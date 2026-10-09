"""Parity of app.ml.pipeline with the ORIGINAL notebook code.

The notebook's own function definitions (cells 0, 2, 4) are extracted with ``ast`` and executed
in a namespace holding the artifact objects, so the reference is the notebook text itself, not a
re-implementation. Tests marked ``model`` need the real predictor.joblib
(env PREDICTOR_ARTIFACT or artifacts/predictor.joblib) and are skipped otherwise.
"""

from __future__ import annotations

import ast
import json

import numpy as np
import pandas as pd
import pytest

from app.ml import pipeline as pl
from app.ml.predictor import PredictionService, raw_to_frame
from app.services.mapper import build_raw
from tests.conftest import FIX, artifact_path

NB_FUNC_CELLS = (0, 2, 4)
NB_ASSIGNS = {"first", "hcols", "s2c", "s5c", "P_COLS", "RAW_COLS", "SUPPORTED", "KAPPA", "SEED"}


def _targets(node: ast.Assign) -> set[str]:
    names: set[str] = set()
    for t in node.targets:
        for n in ast.walk(t):
            if isinstance(n, ast.Name):
                names.add(n.id)
    return names


def notebook_namespace(**state) -> dict:
    """Execute only function definitions + the small constant assignments of the notebook."""
    nb = json.loads((FIX / "model_train.ipynb").read_text(encoding="utf-8"))
    ns: dict = {"np": np, "pd": pd, **state}
    for ci in NB_FUNC_CELLS:
        for node in ast.parse("".join(nb["cells"][ci]["source"])).body:
            if isinstance(node, ast.FunctionDef) or (isinstance(node, ast.Assign) and _targets(node) <= NB_ASSIGNS):
                exec(compile(ast.Module([node], []), "model_train.ipynb", "exec"), ns)
    return ns


# ---------------------------------------------------------------- no artifact needed
def test_constants_match_notebook():
    ns = notebook_namespace()
    assert pl.RAW_COLS == ns["RAW_COLS"] and pl.P_COLS == ns["P_COLS"]
    assert pl.SUPPORTED == ns["SUPPORTED"] and pl.KAPPA == ns["KAPPA"]
    assert (pl.hcols, pl.s2c, pl.s5c) == (ns["hcols"], ns["s2c"], ns["s5c"])


def test_index_building_and_lookup_match_notebook_on_small_store():
    rng = np.random.RandomState(0)
    n = 400
    store = pd.DataFrame({
        "purchase_number": [f"p{i}" for i in range(n)],
        "responsible": rng.choice(["111", "222", "333"], n),
        "ptype": rng.choice(pl.SUPPORTED, n),
        "prod2": rng.choice(["01", "22", None], n),
        "prod5": rng.choice(["01.11", "22.21", None], n),
        "proto": pd.to_datetime("2025-01-01") + pd.to_timedelta(rng.randint(0, 400, n), unit="D"),
        "low": rng.rand(n) < .1, "nodrop": rng.rand(n) < .3, "ratio": rng.rand(n),
    })
    store[["low", "nodrop"]] = store[["low", "nodrop"]].astype(float)
    gm = np.array([.05, .36, .78])
    ns = notebook_namespace(store=store, GM=gm)
    ns["IDX"] = ns["build_all_indexes"]()
    mine = pl.build_all_indexes(store)
    assert {k: sorted(v) for k, v in mine.items()} == {k: sorted(v) for k, v in ns["IDX"].items()}
    pub = pd.to_datetime(["2024-12-01", "2025-06-01", "2026-12-31", "2025-06-01"]).to_numpy(dtype="datetime64[ns]")
    args = (pd.Series(["111", "222", "999", "333"]), ["epNotificationEZK2020"] * 4, ["01", "22", None, "01"],
            ["01.11", "22.21", None, "01.11"], pub)
    pd.testing.assert_frame_equal(pl.history_features(*args, mine, gm), ns["history_features"](*args))


def test_mix_median_matches_notebook():
    ns = notebook_namespace()
    rs = np.random.RandomState(1)
    P = rs.dirichlet([1, 1, 1], 200)
    r = rs.rand(200)
    np.testing.assert_array_equal(pl.mix_median(P, r), ns["mix_median"](P, r))


def test_raw_frame_has_notebook_schema_and_null_semantics(ezk_purchase):
    raw = build_raw({**ezk_purchase, "object_info": None})
    df = raw_to_frame([raw])
    assert list(df.columns) == pl.RAW_COLS
    assert pd.isna(df.loc[0, "object_info"]) and pd.api.types.is_string_dtype(df["object_info"])
    X = pl.base_features(pl.add_codes(df.copy()), {"purchase_type": pd.Index(sorted(pl.SUPPORTED)), "okpd2_2": pd.Index(["22"])})
    assert np.isnan(X.loc[0, "txt_len"])          # NaN, as in training - NOT 0


def test_missing_organizer_uses_notebook_sentinel_and_does_not_crash():
    df = raw_to_frame([{"purchase_number": "1", "purchase_type": "epNotificationEF2020", "responsible": None,
                        "published_at_ts": "2026-01-01T00:00:00", "max_price": 10.0}])
    assert df.loc[0, "responsible"] == "__NA__"


# ---------------------------------------------------------------- real artifact
pytestmark_model = pytest.mark.skipif(artifact_path() is None, reason="predictor.joblib not available")


@pytest.fixture(scope="session")
def bundle():
    return pl.ModelBundle.load(artifact_path())


@pytest.fixture(scope="session")
def nb(bundle):
    """Notebook functions bound to the artifact's models and the (identically built) indexes."""
    ns = notebook_namespace(CATS=bundle.CATS, GM=bundle.GM, vec=bundle.vec, text_models=bundle.text_models,
                            clf=bundle.clf, reg=bundle.reg, l2=bundle.l2, FEATS=bundle.FEATS, IDX=bundle.IDX)
    return ns


def sample_raws(bundle) -> list[dict]:
    """Rows that hit real organizers / product groups from the history, plus edge cases."""
    keys = list(bundle.IDX["s5"])[:: max(1, len(bundle.IDX["s5"]) // 12)][:12]
    rows = []
    for i, k in enumerate(keys):
        org, ptype, p5 = k.split("|")
        rows.append({
            "purchase_number": f"{i:019d}", "purchase_type": ptype, "responsible": org,
            "published_at": ["2026-01-15T08:00:00", "2026-05-20T12:30:00", "2025-03-03T00:00:01"][i % 3],
            "collecting_finished_at": ["2026-01-22T00:00:00", "2026-05-18T00:00:00", "2025-03-10T09:00:00"][i % 3],
            "max_price": [901989.0, 5.5e6, 120000.0, 3.2e8][i % 4],
            "contract_guarantee_part": [None, 5.0, 10.0][i % 3],
            "ktru": [f"{p5}.123-0000001"] if i % 2 else [], "okpd2": [f"{p5}.9"] if i % 3 == 0 else [],
            "position_numbers": ["a"] * (1 + i % 3),
            "object_info": None if i % 4 == 0 else f"Поставка товара номер {i}, одноразового использования",
        })
    rows += [  # edge cases
        {"purchase_number": "9" * 19, "purchase_type": "epNotificationEZT2020", "responsible": None,
         "published_at": "2026-02-02T00:00:00", "collecting_finished_at": None, "max_price": 1234.5,
         "ktru": [], "okpd2": [], "position_numbers": [], "object_info": None},
        {"purchase_number": "8" * 19, "purchase_type": "epNotificationEF2020", "responsible": "0000000000",
         "published_at": "2024-06-01T00:00:00", "collecting_finished_at": "2024-06-02T00:00:00", "max_price": 50.0,
         "ktru": ["99.99.99.999-00000001"], "okpd2": ["99.99.9"], "position_numbers": ["x"], "object_info": "ааа"},
    ]
    return rows


@pytest.mark.model
@pytestmark_model
def test_feature_order_matches_artifact(bundle):
    df = raw_to_frame([build_raw(r) for r in sample_raws(bundle)])
    X = bundle.build_X(df)
    assert list(X.columns) == list(bundle.FEATS)
    assert list(bundle.clf.feature_name_) == list(bundle.FEATS)


@pytest.mark.model
@pytestmark_model
def test_features_and_predictions_identical_to_notebook(bundle, nb):
    raws = [build_raw(r) for r in sample_raws(bundle)]
    df = raw_to_frame(raws)
    X_mine, X_nb = bundle.build_X(df), nb["build_X"](df)
    pd.testing.assert_frame_equal(X_mine, X_nb, check_exact=True)
    pd.testing.assert_frame_equal(bundle.predict(df), nb["predict"](df), check_exact=True)
    assert X_mine["r_n"].gt(0).any() and X_mine["r_n"].eq(0).any()     # history is really exercised


@pytest.mark.model
@pytestmark_model
def test_missing_organizer_falls_back_to_global_prior(bundle, ezk_purchase):
    X = bundle.build_X(raw_to_frame([build_raw({**ezk_purchase, "responsible": None})]))
    # notebook semantics: organizer-level rates are NaN without history; the global prior flows
    # into the group-level features (shrinkage target) instead
    assert X.loc[0, "r_n"] == 0 and X[["r_low", "r_nodrop", "r_ratio"]].isna().all(axis=None)
    assert X.loc[0, "s2_n"] == 0
    assert [X.loc[0, "s2_low"], X.loc[0, "s2_nodrop"], X.loc[0, "s2_ratio"]] == pytest.approx(list(bundle.GM))
    assert np.isfinite(bundle.predict(raw_to_frame([build_raw({**ezk_purchase, "responsible": None})])).iloc[0]["predicted_price"])


@pytest.mark.model
@pytestmark_model
def test_history_is_point_in_time(bundle):
    """A tender published before the store starts sees no history; a later one sees it."""
    base = build_raw(json.loads((FIX / "gosplan_ezk_purchase.json").read_text(encoding="utf-8")))
    early = raw_to_frame([{**base, "published_at_ts": "2024-06-01T00:00:00", "collecting_finished_at_ts": "2024-06-08T00:00:00"}])
    late = raw_to_frame([{**base, "published_at_ts": "2026-05-30T00:00:00"}])
    assert bundle.build_X(early).loc[0, "r_n"] == 0
    assert bundle.build_X(late).loc[0, "r_n"] > bundle.build_X(raw_to_frame([base])).loc[0, "r_n"] - 1


@pytest.mark.model
@pytestmark_model
def test_known_example_matches_notebook_run(bundle, ezk_purchase):
    """Numbers produced by running the notebook code against the real artifact (2026-10)."""
    with_text = bundle.predict(raw_to_frame([build_raw(ezk_purchase)])).iloc[0]
    assert with_text["ratio_median"] == pytest.approx(0.775, abs=1e-9)
    assert with_text["ratio_mean"] == pytest.approx(0.7309, abs=2e-4)
    assert with_text["p_nodrop"] == pytest.approx(0.0474, abs=2e-4)
    assert with_text["predicted_price"] == pytest.approx(699041.475, rel=1e-6)
    no_text = bundle.predict(raw_to_frame([build_raw({**ezk_purchase, "object_info": None})])).iloc[0]
    assert no_text["ratio_median"] == pytest.approx(0.92, abs=1e-9)
    assert no_text["ratio_mean"] == pytest.approx(0.898, abs=2e-4)


@pytest.mark.model
@pytestmark_model
def test_service_end_to_end_on_real_model(bundle, ezk_purchase):
    svc = PredictionService("unused")
    svc.set_bundle(bundle)
    good = build_raw(ezk_purchase)
    eok = {**good, "purchase_type": "epNotificationEOK2020"}
    no_price = {**good, "max_price": None}
    res = svc.predict_many([good, eok, no_price, {**good, "published_at_ts": None}])
    assert [r.ok for r in res] == [True, False, False, False]
    assert "not supported" in res[1].reason and "maximum price" in res[2].reason and "publication date" in res[3].reason
    r = res[0].result
    assert r["predicted_price"] == pytest.approx(699041.475, rel=1e-6)
    assert r["expected_discount_pct"] == pytest.approx(22.5)
    assert r["p_low"] + r["p_partial"] + r["p_nodrop"] == pytest.approx(1.0)
    assert r["history"]["organizer_n"] > 0
    assert svc.status()["history_until"].startswith("2026-06")
