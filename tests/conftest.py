from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import Context
from app.config import Settings
from app.main import create_app
from app.ml.predictor import Prediction, PredictionService, check_raw
from app.services.db import Database
from app.services.gosplan import GosplanError
from app.services.tender_service import TenderService

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[1]


def load_fixture(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def ezk_purchase() -> dict[str, Any]:
    return load_fixture("gosplan_ezk_purchase.json")


@pytest.fixture
def ezk_protocols() -> list[Any]:
    return load_fixture("gosplan_ezk_protocols.json")


def artifact_path() -> Path | None:
    """Model for the heavy tests: PREDICTOR_ARTIFACT (folder or .joblib), else ./artifacts/hf_model, else the legacy file."""
    for cand in (os.getenv("PREDICTOR_ARTIFACT"), str(ROOT / "artifacts" / "hf_model"), str(ROOT / "artifacts" / "predictor.joblib")):
        if cand and Path(cand).exists():
            return Path(cand)
    return None


class FakeGosplan:
    """Dict-backed stand-in for GosplanClient."""

    def __init__(self):
        self.purchases: dict[str, dict] = {}
        self.protocols: dict[str, list] = {}
        self.errors: dict[str, GosplanError] = {}
        self.calls: list[str] = []

    async def get_purchase(self, pn: str):
        self.calls.append(f"purchase:{pn}")
        if pn in self.errors:
            raise self.errors[pn]
        if pn not in self.purchases:
            raise GosplanError("not_found", "Not found in GosPlan (HTTP 404)", 404)
        return copy.deepcopy(self.purchases[pn])

    async def get_protocols(self, pn: str):
        self.calls.append(f"protocols:{pn}")
        if pn in self.protocols:
            return copy.deepcopy(self.protocols[pn])
        raise GosplanError("not_found", "Not found in GosPlan (HTTP 404)", 404)

    async def download_purchase(self, pn: str) -> bytes:
        if pn in self.errors:
            raise self.errors[pn]
        if pn not in self.purchases:
            raise GosplanError("not_found", "Not found in GosPlan (HTTP 404)", 404)
        return json.dumps(self.purchases[pn], ensure_ascii=False).encode()

    async def aclose(self):
        pass


class FakePredictor(PredictionService):
    """Real validation (check_raw), deterministic fake numbers - no model needed."""

    def __init__(self, ready: bool = True):
        super().__init__("/nonexistent")
        self._state = "ready" if ready else "loading"
        self._fake_ready = ready

    @property
    def ready(self) -> bool:
        return self._fake_ready

    def predict_many(self, raws):
        if not self._fake_ready:  # real not-ready behaviour
            return super().predict_many(raws)
        out = []
        for r in raws:
            reason = check_raw(r)
            if reason:
                out.append(Prediction(False, reason))
                continue
            mp = float(r["max_price"])
            res = {
                "max_price": mp, "predicted_price": mp * 0.8, "predicted_price_for_sums": mp * 0.75,
                "ratio_median": 0.8, "ratio_mean": 0.75, "expected_discount_pct": 20.0, "expected_discount_pct_mean": 25.0,
                "p_low": 0.05, "p_nodrop": 0.25, "p_partial": 0.7, "most_likely_outcome": "partial_drop",
                "typical_error_ratio": 0.15, "history": {"organizer_n": 3, "group2_n": 2, "group5_n": 1}, "warnings": [],
            }
            out.append(Prediction(True, None, res, []))
        return out


def make_purchase(base: dict, pn: str, **over) -> dict:
    d = copy.deepcopy(base)
    d["purchase_number"] = pn
    d.update(over)
    return d


@pytest.fixture
def fake_gosplan(ezk_purchase, ezk_protocols):
    g = FakeGosplan()
    g.purchases["0320300101526000015"] = ezk_purchase
    g.protocols["0320300101526000015"] = ezk_protocols
    return g


@pytest.fixture
def make_client(fake_gosplan):
    def _make(ready: bool = True) -> TestClient:
        db = Database(":memory:")
        pred = FakePredictor(ready)
        svc = TenderService(db, fake_gosplan, pred, max_batch=50)
        ctx = Context(Settings.from_env(), db, fake_gosplan, pred, svc)
        return TestClient(create_app(ctx=ctx))

    return _make


@pytest.fixture
def client(make_client):
    with make_client() as c:
        yield c
