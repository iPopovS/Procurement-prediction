"""Tender endpoints: upload, list/detail, predict, delete, GosPlan JSON download proxy."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.api.deps import Context, get_ctx, get_filters
from app.api.schemas import TenderList, UploadRequest, UploadResponse
from app.services.db import SORTS, Filters
from app.services.gosplan import GosplanError
from app.services.mapper import PURCHASE_NUMBER_RE
from app.services.tender_service import BatchTooLarge, NotFound

router = APIRouter(prefix="/api/tenders", tags=["tenders"])

_STATUS_FOR_KIND = {"not_found": 404, "timeout": 504, "unavailable": 502, "bad_response": 502, "http_error": 502}


def _model_ready(ctx: Context) -> None:
    if not ctx.predictor.ready:
        st = ctx.predictor.status()
        msg = (
            "The model is still loading (1-2 minutes after start). Try again shortly."
            if st["state"] in ("idle", "loading")
            else f"The model is not available: {st.get('error')}"
        )
        raise HTTPException(503, msg)


@router.post("", response_model=UploadResponse, summary="Upload purchase numbers and/or full records")
async def upload(body: UploadRequest, ctx: Context = Depends(get_ctx)):
    if not body.purchase_numbers and not body.records:
        raise HTTPException(422, "Provide `purchase_numbers` and/or `records`.")
    try:
        return await ctx.service.ingest(
            body.purchase_numbers, body.records, body.predict, body.fetch_winner, body.skip_existing
        )
    except BatchTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc


def parse_upload_file(name: str, data: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    """CSV/TXT -> purchase numbers (+ optional winner_price column); JSON -> numbers and/or records."""
    text = data.decode("utf-8-sig", errors="replace")
    if name.lower().endswith(".json") or text.lstrip().startswith(("[", "{")):
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc.msg} (line {exc.lineno})") from exc
        if isinstance(doc, dict) and ("purchase_numbers" in doc or "records" in doc):
            return [str(x) for x in doc.get("purchase_numbers") or []], list(doc.get("records") or [])
        if isinstance(doc, dict):
            doc = [doc]
        nums: list[str] = []
        recs: list[dict[str, Any]] = []
        for x in doc if isinstance(doc, list) else []:
            if isinstance(x, dict):
                recs.append(x)
            elif x is not None:
                nums.append(str(x))
        return nums, recs
    rows = list(csv.reader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ","))
    rows = [r for r in rows if r and any(c.strip() for c in r)]
    if not rows:
        return [], []
    header = [c.strip().lower() for c in rows[0]]
    if "purchase_number" in header:
        pi = header.index("purchase_number")
        wi = header.index("winner_price") if "winner_price" in header else None
        nums, recs = [], []
        for r in rows[1:]:
            if pi >= len(r) or not r[pi].strip():
                continue
            if wi is not None and wi < len(r) and r[wi].strip():
                recs_item = {"purchase_number": r[pi].strip(), "_winner_only": r[wi].strip()}
                recs.append(recs_item)
            else:
                nums.append(r[pi].strip())
        return nums, recs
    # no header: numbers anywhere in the text (one per line / comma / space separated)
    return re.findall(r"\d{8,25}", text), []


@router.post("/upload", response_model=UploadResponse, summary="Upload a CSV / TXT / JSON file")
async def upload_file(
    file: UploadFile = File(..., description="CSV or TXT (one number per line, or a `purchase_number` column, "
                            "optional `winner_price` column) or JSON (list of numbers/records)"),
    predict: bool = Form(False),
    fetch_winner: bool = Form(True),
    skip_existing: bool = Form(False),
    ctx: Context = Depends(get_ctx),
):
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "File is larger than 20 MB.")
    try:
        numbers, records = parse_upload_file(file.filename or "", data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # CSV rows with a winner_price column carry only a number: fetch the tender, then override the winner
    winner_overrides = {r["purchase_number"]: r["_winner_only"] for r in records if "_winner_only" in r}
    records = [r for r in records if "_winner_only" not in r]
    if not numbers and not records and not winner_overrides:
        raise HTTPException(422, "No purchase numbers found in the file.")
    try:
        report = await ctx.service.ingest(
            numbers + list(winner_overrides), records, predict, fetch_winner, skip_existing
        )
    except BatchTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    if winner_overrides:
        report = await _apply_winner_overrides(ctx, report, winner_overrides)
    return report


async def _apply_winner_overrides(ctx: Context, report: dict[str, Any], overrides: dict[str, str]) -> dict[str, Any]:
    from app.services.util import to_float
    from app.services.winner import WinnerResult, validate_price

    for item in report["results"]:
        raw_value = overrides.get(item["purchase_number"])
        if raw_value is None or item["status"] not in ("created", "updated"):
            continue
        detail = await asyncio.to_thread(ctx.db.get, item["purchase_number"])
        price, problem = validate_price(to_float(raw_value), detail["max_price"] if detail else None)
        if price is None:
            item["winner_note"] = f"uploaded winner_price ignored: {problem or 'not a number'}"
            continue
        await asyncio.to_thread(ctx.db.set_winner, item["purchase_number"], WinnerResult(price, "uploaded", None, None))
        item["winner_price"], item["winner_note"] = price, None
    report["summary"]["with_winner_price"] = sum(r.get("winner_price") is not None for r in report["results"])
    return report


@router.get("", response_model=TenderList, summary="List / search tenders")
async def list_tenders(
    f: Filters = Depends(get_filters),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("published_desc", description=" | ".join(SORTS)),
    ctx: Context = Depends(get_ctx),
):
    items, total = await asyncio.to_thread(ctx.db.query, f, limit, offset, sort)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{purchase_number}", summary="Full details of one tender")
async def get_tender(purchase_number: str, ctx: Context = Depends(get_ctx)):
    d = await asyncio.to_thread(ctx.db.get, purchase_number)
    if d is None:
        raise HTTPException(404, "This purchase number is not stored. Upload it first.")
    return d


@router.post("/{purchase_number}/predict", summary="(Re)generate the price prediction")
async def predict_tender(purchase_number: str, ctx: Context = Depends(get_ctx)):
    _model_ready(ctx)
    try:
        return await ctx.service.predict_stored(purchase_number)
    except NotFound as exc:
        raise HTTPException(404, "This purchase number is not stored. Upload it first.") from exc


@router.post("/{purchase_number}/winner", summary="Re-check the winner price in GosPlan protocols")
async def refresh_winner(purchase_number: str, ctx: Context = Depends(get_ctx)):
    try:
        return await ctx.service.refresh_winner(purchase_number)
    except NotFound as exc:
        raise HTTPException(404, "This purchase number is not stored. Upload it first.") from exc


@router.delete("/{purchase_number}", status_code=204, summary="Delete a stored tender")
async def delete_tender(purchase_number: str, ctx: Context = Depends(get_ctx)):
    if not await asyncio.to_thread(ctx.db.delete, purchase_number):
        raise HTTPException(404, "This purchase number is not stored.")
    return Response(status_code=204)


@router.get("/{purchase_number}/download", summary="Proxy: raw GosPlan JSON of the purchase")
async def download(purchase_number: str, ctx: Context = Depends(get_ctx)):
    if not PURCHASE_NUMBER_RE.match(purchase_number):
        raise HTTPException(422, "Not a valid purchase number.")
    try:
        body = await ctx.gosplan.download_purchase(purchase_number)
    except GosplanError as exc:
        raise HTTPException(_STATUS_FOR_KIND.get(exc.kind, 502), exc.message) from exc
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{purchase_number}.json"'},
    )
