"""Service layer around :mod:`app.ml.pipeline`.

Responsibilities:
* load the artifact bundle once, in a background thread (the API stays responsive);
* turn "raw" dicts (the RAW_COLS contract) into the DataFrame the pipeline expects;
* decide up-front whether a tender can be predicted and explain why not;
* never raise to callers - every failure becomes a readable ``reason``.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.ml import pipeline as pl
from app.services.util import parse_dt, str_list, to_float

log = logging.getLogger(__name__)

TYPE_LABELS = {
    "epNotificationEF2020": "EF",
    "epNotificationEZK2020": "EZK",
    "epNotificationEZT2020": "EZT",
}

def type_label(purchase_type: str | None) -> str | None:
    """EF / EZK / EZT for the supported types; ``epNotificationEOK2020`` -> ``EOK`` for any other."""
    if not purchase_type:
        return None
    if purchase_type in TYPE_LABELS:
        return TYPE_LABELS[purchase_type]
    m = re.fullmatch(r"epNotification([A-Za-z0-9]+?)\d{4}", purchase_type)
    return m.group(1) if m else purchase_type


# Typical absolute error of the median head, in units of max_price, from the model README
# (section 3: MAE ~0.150 overall; "EZT purchases are nearly solved (MAE about 0.03)").
# Informational only - the model produces no confidence interval.
TYPICAL_ERROR_RATIO = {"default": 0.15, "epNotificationEZT2020": 0.03}

# pipeline.make_keys is meant to treat a missing organizer as the key "__NA__" (no organizer
# history -> global prior), but under pandas 3 its `astype(str)` keeps NaN and then crashes on
# `NaN + "|"`. Training data never had a null `responsible`, so the notebook never hit this.
# Rather than edit the ported function, a missing organizer is passed as that same sentinel
# string: the org index has no "__NA__" key (the notebook pops it), so the outcome is exactly the
# intended one (n=0 -> global prior).
MISSING_ORG = "__NA__"

PREDICT_CHUNK = 2000
STALE_HISTORY_DAYS = 14


@dataclass
class Prediction:
    ok: bool
    reason: str | None = None
    result: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


def check_raw(raw: dict[str, Any]) -> str | None:
    """Return a human-readable reason if the tender cannot be predicted, else None."""
    ptype = raw.get("purchase_type")
    if not ptype:
        return "The purchase type is missing in the GosPlan record."
    if ptype not in pl.SUPPORTED:
        supported = ", ".join(TYPE_LABELS.values())
        return f"Purchase type {ptype} is not supported by the model (supported: {supported})."
    mp = to_float(raw.get("max_price"))
    if mp is None:
        return "The maximum price (max_price) is missing or not a number."
    if mp <= 1:
        return "The maximum price must be greater than 1 RUB."
    if parse_dt(raw.get("published_at_ts")) is None:
        return (
            "The publication date is missing or unreadable. The model needs it to look up "
            "organizer history without leaking future information."
        )
    return None


def raw_to_frame(raws: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the DataFrame in the notebook's RAW_COLS schema.

    Dtype notes (these matter for faithfulness):
    * text columns use pandas' ``str`` dtype so a missing ``object_info`` stays NaN
      (``txt_len`` = NaN exactly as in training - training data had nulls, never ""),
    * timestamps are naive datetime64[ns].
    """

    def dt_col(key: str) -> pd.Series:
        vals = [parse_dt(r.get(key)) for r in raws]
        return pd.Series(pd.to_datetime(vals)).astype("datetime64[ns]")

    def str_col(key: str) -> pd.Series:
        vals = [None if r.get(key) in (None, "") else str(r[key]) for r in raws]
        return pd.Series(vals, dtype="str")

    def org_col() -> pd.Series:
        vals = [MISSING_ORG if r.get("responsible") in (None, "") else str(r["responsible"]) for r in raws]
        return pd.Series(vals, dtype="str")

    def num_col(key: str) -> pd.Series:
        return pd.Series([to_float(r.get(key)) for r in raws], dtype="float64")

    def list_col(key: str) -> pd.Series:
        s = pd.Series([None] * len(raws), dtype=object)
        for i, r in enumerate(raws):
            s.iat[i] = str_list(r.get(key))
        return s

    df = pd.DataFrame(
        {
            "purchase_number": str_col("purchase_number"),
            "purchase_type": str_col("purchase_type"),
            "responsible": org_col(),
            "published_at_ts": dt_col("published_at_ts"),
            "collecting_finished_at_ts": dt_col("collecting_finished_at_ts"),
            "max_price": num_col("max_price"),
            "contract_guarantee_part": num_col("contract_guarantee_part"),
            "ktru_cnt": pd.Series([int(r.get("ktru_cnt") or 0) for r in raws], dtype="int64"),
            "okpd2_cnt": pd.Series([int(r.get("okpd2_cnt") or 0) for r in raws], dtype="int64"),
            "position_numbers_cnt": pd.Series(
                [int(r.get("position_numbers_cnt") or 0) for r in raws], dtype="int64"
            ),
            "object_info": str_col("object_info"),
            "okpd2": list_col("okpd2"),
            "ktru": list_col("ktru"),
        }
    )
    return df[pl.RAW_COLS]


class PredictionService:
    """Thread-safe holder for the model bundle."""

    def __init__(self, artifact_path: str | Path):
        self.artifact_path = Path(artifact_path)
        self._bundle: pl.ModelBundle | None = None
        self._state = "idle"  # idle | loading | ready | error
        self._error: str | None = None
        self._loaded_at: float | None = None
        self._lock = threading.Lock()  # serialises inference (LightGBM + sklearn)

    # -- lifecycle -----------------------------------------------------------------------
    def start_loading(self) -> threading.Thread:
        self._state = "loading"
        t = threading.Thread(target=self._load, name="model-loader", daemon=True)
        t.start()
        return t

    def _load(self) -> None:
        try:
            if not self.artifact_path.exists():
                raise FileNotFoundError(
                    f"Model not found at {self.artifact_path}. Download the model folder from Hugging Face "
                    "into ./artifacts/hf_model (see README, section 'Model files')."
                )
            self._bundle = pl.ModelBundle.load(self.artifact_path)
            self._loaded_at = time.time()
            self._state = "ready"
            log.info("model ready")
        except Exception as exc:  # noqa: BLE001 - surfaced via status()
            log.exception("model loading failed")
            self._error = f"{type(exc).__name__}: {exc}"
            self._state = "error"

    def set_bundle(self, bundle: pl.ModelBundle) -> None:
        """Inject an already-built bundle (tests)."""
        self._bundle = bundle
        self._state = "ready"

    @property
    def ready(self) -> bool:
        return self._state == "ready" and self._bundle is not None

    def status(self) -> dict[str, Any]:
        info: dict[str, Any] = {"state": self._state, "ready": self.ready, "error": self._error}
        if self._bundle is not None:
            st = self._bundle.store_stats
            info["history_rows"] = st.rows
            info["history_until"] = st.last_protocol.isoformat()
            info["history_from"] = st.first_protocol.isoformat()
            m = self._bundle.meta
            info["model_format"] = m.format
            info["model_version"] = m.version
            info["trained_through"] = m.trained_through
            info["library_warnings"] = m.warnings
        return info

    # -- prediction ----------------------------------------------------------------------
    def predict_many(self, raws: list[dict[str, Any]]) -> list[Prediction]:
        """Predict a list of raw tenders. Output order == input order. Never raises."""
        out: list[Prediction | None] = [None] * len(raws)
        if not self.ready:
            msg = {
                "loading": "The model is still loading (this takes 1-2 minutes after start). Try again shortly.",
                "error": f"The model failed to load: {self._error}",
            }.get(self._state, "The model is not loaded.")
            return [Prediction(False, msg) for _ in raws]

        eligible: list[int] = []
        for i, raw in enumerate(raws):
            reason = check_raw(raw)
            if reason:
                out[i] = Prediction(False, reason)
            else:
                eligible.append(i)

        for start in range(0, len(eligible), PREDICT_CHUNK):
            idxs = eligible[start : start + PREDICT_CHUNK]
            chunk = [raws[i] for i in idxs]
            try:
                results = self._predict_chunk(chunk)
            except Exception:  # noqa: BLE001 - isolate the offending row(s)
                log.exception("batch prediction failed; retrying row by row")
                results = []
                for r in chunk:
                    try:
                        results.extend(self._predict_chunk([r]))
                    except Exception as exc:  # noqa: BLE001
                        log.exception("prediction failed for %s", r.get("purchase_number"))
                        results.append(Prediction(False, f"Prediction failed unexpectedly ({type(exc).__name__})."))
            for i, res in zip(idxs, results, strict=True):
                out[i] = res
        return [o if o is not None else Prediction(False, "No result.") for o in out]

    def predict_one(self, raw: dict[str, Any]) -> Prediction:
        return self.predict_many([raw])[0]

    def _predict_chunk(self, chunk: list[dict[str, Any]]) -> list[Prediction]:
        bundle = self._bundle
        assert bundle is not None
        df = raw_to_frame(chunk)
        with self._lock:
            res, X = bundle.predict_with_features(df)
        if len(res) != len(chunk):  # pipeline filtered something we considered eligible
            raise RuntimeError("pipeline dropped rows that passed validation")
        last_proto = bundle.store_stats.last_protocol
        preds: list[Prediction] = []
        for i, raw in enumerate(chunk):
            row = res.iloc[i]
            xr = X.iloc[i]
            vals = [row[c] for c in ("p_low", "p_nodrop", "ratio_median", "ratio_mean", "predicted_price")]
            if not all(math.isfinite(float(v)) for v in vals):
                preds.append(Prediction(False, "The model returned a non-finite value for this tender."))
                continue
            preds.append(self._format(raw, row, xr, last_proto))
        return preds

    @staticmethod
    def _format(raw: dict[str, Any], row: pd.Series, xr: pd.Series, last_proto: pd.Timestamp) -> Prediction:
        max_price = float(row["max_price"])
        p_low, p_nodrop = float(row["p_low"]), float(row["p_nodrop"])
        p_partial = max(0.0, 1.0 - p_low - p_nodrop)
        r_med, r_mean = float(row["ratio_median"]), float(row["ratio_mean"])
        likely = max(
            (("very_low", p_low), ("partial_drop", p_partial), ("no_drop", p_nodrop)),
            key=lambda kv: kv[1],
        )[0]
        err_ratio = TYPICAL_ERROR_RATIO.get(raw.get("purchase_type"), TYPICAL_ERROR_RATIO["default"])

        def n(v: Any) -> int:
            return 0 if v is None or (isinstance(v, float) and np.isnan(v)) else int(v)

        warnings: list[str] = []
        if not raw.get("responsible"):
            warnings.append("Organizer ID is missing, so organizer history was not used (global averages applied).")
        elif n(xr["r_n"]) == 0:
            warnings.append(
                "No earlier finished purchases from this organizer were found in the model's history; "
                "global averages were used for the organizer signal."
            )
        if not str_list(raw.get("okpd2")) and not str_list(raw.get("ktru")):
            warnings.append("No OKPD2/KTRU codes: product-group history could not be used.")
        if raw.get("object_info") in (None, ""):
            warnings.append("The object description is empty, so text signals were not available.")
        pub = parse_dt(raw.get("published_at_ts"))
        if pub is not None and (pub - last_proto.to_pydatetime()).days > STALE_HISTORY_DAYS:
            warnings.append(
                f"The model's history ends on {last_proto:%Y-%m-%d}; this tender was published later, "
                "so recent organizer behavior is not reflected."
            )
        cur = raw.get("currency_code")
        if cur and cur != "RUB":
            warnings.append(f"Currency is {cur}; the model was trained on RUB prices.")

        result = {
            "max_price": max_price,
            "predicted_price": float(row["predicted_price"]),
            "predicted_price_for_sums": float(row["predicted_price_for_sums"]),
            "ratio_median": r_med,
            "ratio_mean": r_mean,
            "expected_discount_pct": (1.0 - r_med) * 100.0,
            "expected_discount_pct_mean": (1.0 - r_mean) * 100.0,
            "p_low": p_low,
            "p_nodrop": p_nodrop,
            "p_partial": p_partial,
            "most_likely_outcome": likely,
            "typical_error_ratio": err_ratio,
            "history": {
                "organizer_n": n(xr["r_n"]),
                "group2_n": n(xr["s2_n"]),
                "group5_n": n(xr["s5_n"]),
            },
            "warnings": warnings,
        }
        return Prediction(True, None, result, warnings)
