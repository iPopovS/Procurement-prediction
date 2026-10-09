"""Feature pipeline + prediction, ported from ``model_train.ipynb``.

The function bodies below are copied from the notebook (cells 0, 2 and 4) with ONE
mechanical change: notebook globals (``CATS``, ``IDX``, ``GM``, ``store``, ``vec``,
``text_models``, ``clf``, ``reg``, ``l2``, ``FEATS``) are passed explicitly or held on
:class:`ModelBundle`. Logic, operation order and constants are unchanged.

Do NOT "improve" this file. ``tests/test_pipeline_parity.py`` executes the notebook's
own function definitions and compares outputs with this module.

Notebook cell -> function here
    cell 0: first, add_codes, base_features
    cell 2: make_keys, build_index, build_all_indexes, lookup, history_features
    cell 4: mix_median, predict_X, build_X, predict
"""

from __future__ import annotations

import gc
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from app.ml import manifest as mf

log = logging.getLogger(__name__)

# ---- constants (notebook cell 0 / cell 2) -------------------------------------------
KAPPA = 10
SUPPORTED = ["epNotificationEF2020", "epNotificationEZK2020", "epNotificationEZT2020"]
P_COLS = [
    "purchase_number", "purchase_type", "responsible", "published_at_ts",
    "collecting_finished_at_ts", "max_price", "contract_guarantee_part",
    "ktru_cnt", "okpd2_cnt", "position_numbers_cnt", "object_info",
]
RAW_COLS = P_COLS + ["okpd2", "ktru"]  # schema of a raw notice

hcols = ["r_n", "r_low", "r_nodrop", "r_ratio"]
s2c = ["s2_n", "s2_low", "s2_nodrop", "s2_ratio"]
s5c = ["s5_n", "s5_low", "s5_nodrop", "s5_ratio"]


def first(a):
    return a[0] if a is not None and len(a) > 0 else None


# ---- notebook cell 0 ------------------------------------------------------------------
def add_codes(df):
    """first OKPD2 code, KTRU fallback, 2- and 5-char product keys"""
    df["okpd2_1"] = df["okpd2"].map(first)
    df["ktru_1"] = df["ktru"].map(first)
    code = df["okpd2_1"].fillna(df["ktru_1"])
    df["prod2"], df["prod5"] = code.str[:2], code.str[:5]
    return df


def base_features(df, cats):
    X = pd.DataFrame(index=df.index)
    X["purchase_type_c"] = pd.Categorical(df["purchase_type"], categories=cats["purchase_type"])
    X["log_max"] = np.log1p(df["max_price"])
    X["contract_guarantee_part"] = df["contract_guarantee_part"]
    lead = (df["collecting_finished_at_ts"] - df["published_at_ts"]).dt.total_seconds() / 86400
    X["lead_days"] = lead.where(lead >= 0).clip(upper=40)
    for c in ["ktru_cnt", "okpd2_cnt", "position_numbers_cnt"]:
        X[c] = df[c]
    X["okpd2_2_c"] = pd.Categorical(df["okpd2_1"].str[:2], categories=cats["okpd2_2"])
    X["txt_len"] = df["object_info"].str.len()
    return X


# ---- notebook cell 2 ------------------------------------------------------------------
def make_keys(resp, ptype, prod2, prod5):
    resp = pd.Series(np.asarray(resp, dtype=object))
    isna = resp.isna().to_numpy()
    r = resp.astype(str).to_numpy(dtype=object)
    pt = pd.Series(np.asarray(ptype, dtype=object)).astype(str).to_numpy(dtype=object)
    base = r + "|" + pt + "|"
    k2 = base + pd.Series(np.asarray(prod2, dtype=object)).fillna("NA").to_numpy(dtype=object)
    k5 = base + pd.Series(np.asarray(prod5, dtype=object)).fillna("NA").to_numpy(dtype=object)
    return np.where(isna, "__NA__", r).astype(object), k2, k5


def build_index(keys, store):
    vals = np.c_[np.ones(len(store)), store[["low", "nodrop", "ratio"]].to_numpy()]
    prt = store["proto"].to_numpy(dtype="datetime64[ns]")
    out = {}
    for k, ix in pd.Series(np.arange(len(store))).groupby(np.asarray(keys, dtype=object)).indices.items():
        o = ix[np.argsort(prt[ix])]
        out[k] = (prt[o], np.vstack([np.zeros((1, 4)), np.cumsum(vals[o], axis=0)]))
    return out


def build_all_indexes(store):
    ko, k2, k5 = make_keys(store["responsible"], store["ptype"], store["prod2"], store["prod5"])
    idx = {"org": build_index(ko, store), "s2": build_index(k2, store), "s5": build_index(k5, store)}
    idx["org"].pop("__NA__", None)
    return idx


def lookup(index, keys, pub):
    n = np.zeros(len(keys))
    s = np.zeros((len(keys), 3))
    for k, ix in pd.Series(np.arange(len(keys))).groupby(np.asarray(keys, dtype=object)).indices.items():
        if k in index:
            pr, cs = index[k]
            k1 = np.searchsorted(pr, pub[ix], side="left")  # only protocols strictly before publication
            n[ix] = cs[k1, 0]
            s[ix] = cs[k1, 1:]
    return n, s


def history_features(resp, ptype, prod2, prod5, pub, idx, gm):
    ko, k2, k5 = make_keys(resp, ptype, prod2, prod5)
    n0, s0 = lookup(idx["org"], ko, pub)
    r0 = np.where(n0[:, None] > 0, s0 / np.maximum(n0, 1)[:, None], np.nan)
    org = np.where(np.isnan(r0), gm, r0)
    n2, s2 = lookup(idx["s2"], k2, pub)
    r2 = (s2 + KAPPA * org) / (n2 + KAPPA)[:, None]
    n5, s5 = lookup(idx["s5"], k5, pub)
    r5 = (s5 + KAPPA * r2) / (n5 + KAPPA)[:, None]
    return pd.DataFrame(np.c_[n0, r0, n2, r2, n5, r5], columns=hcols + s2c + s5c)


# ---- notebook cell 4 ------------------------------------------------------------------
def mix_median(P, r):
    grid = np.linspace(0, 1, 201)
    cdf = P[:, [0]] * (grid >= 0.002) + P[:, [1]] * (grid[None, :] >= r[:, None])
    med = grid[(cdf >= 0.5).argmax(1)]
    return np.where(P[:, 0] + P[:, 1] < 0.5, 1.0, med)


@dataclass
class StoreStats:
    rows: int
    first_protocol: pd.Timestamp
    last_protocol: pd.Timestamp


@dataclass
class ModelMeta:
    """Where the model came from (shown in /api/health)."""

    format: str  # "folder" (Hugging Face export) | "joblib" (legacy single file)
    version: str | None = None
    trained_through: str | None = None
    warnings: list[str] = field(default_factory=list)


class BoosterModel:
    """A LightGBM ``Booster`` loaded from a text model, exposing the two sklearn-style methods the
    notebook's ``predict_X`` calls (``predict_proba`` / ``predict``) so that function stays untouched.

    Verified bit-identical to the original ``LGBMClassifier`` / ``LGBMRegressor`` (the pandas
    category lists are stored inside the text model).
    """

    def __init__(self, path: str | Path):
        self.booster = lgb.Booster(model_file=str(path))

    @property
    def feature_name_(self) -> list[str]:
        return self.booster.feature_name()

    def predict(self, X):
        return self.booster.predict(X)

    def predict_proba(self, X):
        p = self.booster.predict(X)  # multiclass objective -> (n, n_classes) probabilities
        if p.ndim != 2:
            raise ValueError("predict_proba is only valid for the multiclass model")
        return p


STORE_COLUMNS = ["responsible", "ptype", "prod2", "prod5", "proto", "low", "nodrop", "ratio"]


def _read_folder(folder: Path) -> tuple[dict[str, Any], pd.DataFrame, ModelMeta]:
    """Model folder exported by the notebook (see app/ml/manifest.py for the layout)."""
    m = mf.read_manifest(folder)
    mf.verify_files(folder, m)  # sha256 of every file
    text = joblib.load(folder / "text.joblib")
    cfg = joblib.load(folder / "config.joblib")
    store = pd.read_parquet(folder / "store.parquet")
    art = {
        "clf": BoosterModel(folder / "clf.txt"),
        "reg": BoosterModel(folder / "reg.txt"),
        "l2": BoosterModel(folder / "l2.txt"),
        "vec": text["vec"],
        "text_models": text["text_models"],
        "features": cfg["features"],
        "cats": cfg["cats"],
        "gm": cfg["gm"],
        "cap": cfg["cap"],
    }
    meta = ModelMeta("folder", m.get("version"), m.get("trained_through"), mf.library_warnings(m))
    return art, store, meta


def _read_joblib(path: Path) -> tuple[dict[str, Any], pd.DataFrame, ModelMeta]:
    """Legacy single-file bundle (predictor.joblib)."""
    art = joblib.load(path)
    missing = {"clf", "reg", "l2", "features", "vec", "text_models", "cats", "gm", "cap", "store"} - set(art)
    if missing:
        raise ValueError(f"Artifact is missing keys: {sorted(missing)}")
    store = art.pop("store")
    return art, store, ModelMeta("joblib")


class ModelBundle:
    """Holds the trained models plus the history indexes rebuilt from the store.

    Instantiate once at process start via :meth:`load`; all methods are read-only afterwards.
    """

    def __init__(self, art: dict[str, Any], idx: dict, stats: StoreStats, meta: ModelMeta | None = None):
        self.clf = art["clf"]
        self.reg = art["reg"]
        self.l2 = art["l2"]
        self.FEATS = list(art["features"])
        self.vec = art["vec"]
        self.text_models = art["text_models"]
        self.CATS = art["cats"]
        self.GM = art["gm"]
        self.CAP = art["cap"]
        self.IDX = idx
        self.store_stats = stats
        self.meta = meta or ModelMeta("joblib")

    # -- loading ---------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> ModelBundle:
        """``path``: the model folder downloaded from Hugging Face, or a legacy predictor.joblib."""
        path = Path(path)
        t0 = time.time()
        if path.is_dir():
            art, store, meta = _read_folder(path)
        elif path.is_file():
            art, store, meta = _read_joblib(path)
        else:
            raise mf.ModelFilesError(f"Model path not found: {path}")
        absent = [c for c in STORE_COLUMNS if c not in store.columns]
        if absent:
            raise mf.ModelFilesError(f"History store is missing columns: {absent}")
        for w in meta.warnings:
            log.warning("library version differs from training: %s", w)
        log.info("model files (%s) loaded in %.1fs; history store rows=%d", meta.format, time.time() - t0, len(store))
        t1 = time.time()
        idx = build_all_indexes(store)
        stats = StoreStats(
            rows=len(store),
            first_protocol=pd.Timestamp(store["proto"].min()),
            last_protocol=pd.Timestamp(store["proto"].max()),
        )
        log.info(
            "history indexes built in %.1fs (org=%d, s2=%d, s5=%d keys)",
            time.time() - t1, len(idx["org"]), len(idx["s2"]), len(idx["s5"]),
        )
        # The raw store is only needed to build the indexes; release it.
        del store
        gc.collect()
        return cls(art, idx, stats, meta)

    # -- notebook cell 4 -------------------------------------------------------------
    def predict_X(self, X):
        Pk = self.clf.predict_proba(X)
        med = mix_median(Pk, np.clip(self.reg.predict(X), 0, 1))
        mean = np.clip(self.l2.predict(X), 0, 1)
        return Pk, med, mean

    def build_X(self, raw):
        raw = add_codes(raw.reset_index(drop=True).copy())
        X = base_features(raw, self.CATS)
        Xt = self.vec.transform(raw["object_info"].fillna(""))
        X["txt_low"] = self.text_models["low"].predict_proba(Xt)[:, 1]
        X["txt_nodrop"] = self.text_models["nodrop"].predict_proba(Xt)[:, 1]
        H_ = history_features(
            raw["responsible"], raw["purchase_type"], raw["prod2"], raw["prod5"],
            raw["published_at_ts"].to_numpy(dtype="datetime64[ns]"), self.IDX, self.GM,
        )
        return pd.concat([X, H_], axis=1)[self.FEATS]

    def predict(self, raw):
        """raw: notices in the purchases_flat schema (RAW_COLS). Returns predicted winner prices."""
        out, _ = self.predict_with_features(raw)
        return out

    # -- same as notebook ``predict`` but also returns the model input matrix -----------
    def predict_with_features(self, raw):
        raw = raw[raw["purchase_type"].isin(SUPPORTED) & (raw["max_price"] > 1)].reset_index(drop=True)
        X = self.build_X(raw)
        Pk, med, mean = self.predict_X(X)
        out = raw[["purchase_number", "max_price"]].copy()
        out["p_low"], out["p_nodrop"] = Pk[:, 0], Pk[:, 2]
        out["ratio_median"], out["ratio_mean"] = med, mean
        out["predicted_price"] = med * out["max_price"]  # one contract
        out["predicted_price_for_sums"] = mean * out["max_price"]  # budgets / totals
        return out, X
