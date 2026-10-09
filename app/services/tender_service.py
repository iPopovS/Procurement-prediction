"""Orchestration: GosPlan -> mapper -> SQLite -> model. All failures become per-item results."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.ml.predictor import Prediction, PredictionService
from app.services.db import Database
from app.services.gosplan import GosplanClient, GosplanError
from app.services.mapper import PURCHASE_NUMBER_RE, build_tender_record
from app.services.util import to_float
from app.services.winner import WinnerResult, extract_winner_price, validate_price

log = logging.getLogger(__name__)


class NotFound(Exception):
    pass


class BatchTooLarge(Exception):
    pass


@dataclass
class _Item:
    purchase_number: str
    record: dict[str, Any] | None = None  # full GosPlan-shaped record supplied by the caller


def _prediction_block(p: Prediction | None) -> dict[str, Any] | None:
    if p is None:
        return None
    if p.ok and p.result:
        return {
            "status": "ok",
            "predicted_price": p.result["predicted_price"],
            "expected_discount_pct": p.result["expected_discount_pct"],
            "warnings": p.warnings,
        }
    return {"status": "failed", "reason": p.reason}


class TenderService:
    def __init__(self, db: Database, gosplan: GosplanClient, predictor: PredictionService, max_batch: int):
        self.db = db
        self.gosplan = gosplan
        self.predictor = predictor
        self.max_batch = max_batch

    # -- helpers ----------------------------------------------------------------------
    async def _lookup_winner(self, pn: str, max_price: float | None) -> WinnerResult:
        """Winner price for DISPLAY. Lookup problems never fail the item."""
        try:
            protocols = await self.gosplan.get_protocols(pn)
        except GosplanError as exc:
            if exc.kind == "not_found":
                return WinnerResult(note="no protocols published yet")
            return WinnerResult(note=f"winner lookup failed: {exc.message}")
        return extract_winner_price(protocols, max_price)

    async def _process(self, item: _Item, fetch_winner: bool) -> dict[str, Any]:
        """Fetch + map one tender. Returns {'result': ItemResult-dict, 'record': db-record|None}."""
        pn = item.purchase_number
        try:
            response = item.record if item.record is not None else await self.gosplan.get_purchase(pn)
        except GosplanError as exc:
            return {"result": {"purchase_number": pn, "status": "failed", "error": exc.message, "error_kind": exc.kind}, "record": None}

        winner: WinnerResult | None = None
        try:
            max_price = to_float(response.get("max_price"))
            supplied = to_float(response.get("winner_price")) if item.record is not None else None
            if supplied is not None:
                valid, problem = validate_price(supplied, max_price)
                winner = WinnerResult(valid, "uploaded" if valid is not None else None, None, problem)
            if (winner is None or winner.price is None) and fetch_winner:
                looked_up = await self._lookup_winner(pn, max_price)
                winner = looked_up if (winner is None or looked_up.price is not None) else winner
            rec = build_tender_record({**response, "purchase_number": response.get("purchase_number") or pn}, winner)
            if rec["purchase_number"] != pn:  # GosPlan answered with another number; keep what was asked for
                rec["purchase_number"] = pn
                rec["raw"]["purchase_number"] = pn
        except Exception as exc:  # noqa: BLE001 - malformed record must not abort the batch
            log.exception("could not map record %s", pn)
            return {
                "result": {"purchase_number": pn, "status": "failed", "error": f"Could not read the record ({type(exc).__name__}).", "error_kind": "bad_record"},
                "record": None,
            }
        return {"result": {"purchase_number": pn, "status": "pending"}, "record": rec}

    # -- upload -----------------------------------------------------------------------
    async def ingest(
        self,
        purchase_numbers: list[str],
        records: list[dict[str, Any]],
        predict: bool,
        fetch_winner: bool = True,
        skip_existing: bool = False,
    ) -> dict[str, Any]:
        if len(purchase_numbers) + len(records) > self.max_batch:
            raise BatchTooLarge(f"At most {self.max_batch} items per request; send the rest in further requests.")

        results: dict[str, dict[str, Any]] = {}
        items: dict[str, _Item] = {}
        order: list[str] = []

        def add_failed(key: str, msg: str, kind: str) -> None:
            if key not in results:
                order.append(key)
            results[key] = {"purchase_number": key, "status": "failed", "error": msg, "error_kind": kind}

        for rec in records:
            pn = str(rec.get("purchase_number") or "").strip() if isinstance(rec, dict) else ""
            if not PURCHASE_NUMBER_RE.match(pn):
                add_failed(pn or "(no purchase_number)", "The record has no valid purchase_number.", "invalid")
                continue
            if pn not in items:
                order.append(pn)
            items[pn] = _Item(pn, rec)  # a full record wins over a bare number
        for raw_pn in purchase_numbers:
            pn = str(raw_pn).strip()
            if pn in items or pn in results:
                continue
            if not PURCHASE_NUMBER_RE.match(pn):
                add_failed(pn or "(empty)", "Not a valid purchase number (expected 8-25 digits).", "invalid")
                continue
            order.append(pn)
            items[pn] = _Item(pn)

        existing = await asyncio.to_thread(self.db.exists_many, list(items)) if items else set()
        todo: list[_Item] = []
        for pn, it in items.items():
            if skip_existing and pn in existing and it.record is None:
                results[pn] = {"purchase_number": pn, "status": "skipped", "error": None, "note": "already stored"}
            else:
                todo.append(it)

        processed = await asyncio.gather(*(self._process(it, fetch_winner) for it in todo))
        good = [p["record"] for p in processed if p["record"] is not None]
        for p in processed:
            results[p["result"]["purchase_number"]] = p["result"]

        outcome = await asyncio.to_thread(self.db.upsert_many, good) if good else {}
        for pn, state in outcome.items():
            results[pn]["status"] = state  # created | updated
        for rec in good:
            w: WinnerResult | None = rec.get("winner")
            results[rec["purchase_number"]]["winner_price"] = w.price if w else None
            results[rec["purchase_number"]]["winner_note"] = w.note if (w and w.price is None) else None

        if predict and good:
            preds = await self._predict_records([rec["purchase_number"] for rec in good])
            for pn, pred in preds.items():
                results[pn]["prediction"] = _prediction_block(pred)

        ordered = [results[k] for k in order if k in results]
        summary = {
            "requested": len(ordered),
            "created": sum(r["status"] == "created" for r in ordered),
            "updated": sum(r["status"] == "updated" for r in ordered),
            "skipped": sum(r["status"] == "skipped" for r in ordered),
            "failed": sum(r["status"] == "failed" for r in ordered),
            "with_winner_price": sum(r.get("winner_price") is not None for r in ordered),
            "predicted": sum((r.get("prediction") or {}).get("status") == "ok" for r in ordered),
            "prediction_failed": sum((r.get("prediction") or {}).get("status") == "failed" for r in ordered),
        }
        return {"summary": summary, "results": ordered}

    # -- prediction -------------------------------------------------------------------
    async def _predict_records(self, numbers: list[str]) -> dict[str, Prediction]:
        raws: list[dict[str, Any]] = []
        keep: list[str] = []
        for pn in numbers:
            raw = await asyncio.to_thread(self.db.get_raw, pn)
            if raw is not None:
                raws.append(raw)
                keep.append(pn)
        preds = await asyncio.to_thread(self.predictor.predict_many, raws)
        await asyncio.to_thread(self.db.set_predictions, list(zip(keep, preds, strict=True)))
        return dict(zip(keep, preds, strict=True))

    async def predict_stored(self, pn: str) -> dict[str, Any]:
        if not await asyncio.to_thread(self.db.exists_many, [pn]):
            raise NotFound(pn)
        await self._predict_records([pn])
        detail = await asyncio.to_thread(self.db.get, pn)
        assert detail is not None
        return detail

    async def refresh_winner(self, pn: str) -> dict[str, Any]:
        detail = await asyncio.to_thread(self.db.get, pn)
        if detail is None:
            raise NotFound(pn)
        w = await self._lookup_winner(pn, detail["max_price"])
        # Never wipe an already stored winner price just because a re-check found nothing.
        if w.price is not None or detail["winner"]["price"] is None:
            await asyncio.to_thread(self.db.set_winner, pn, w)
        detail = await asyncio.to_thread(self.db.get, pn)
        assert detail is not None
        return detail
