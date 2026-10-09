from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query, Request

from app.config import Settings
from app.ml.predictor import PredictionService
from app.services.db import STATUSES, Database, Filters
from app.services.gosplan import GosplanClient
from app.services.tender_service import TenderService


@dataclass
class Context:
    settings: Settings
    db: Database
    gosplan: GosplanClient
    predictor: PredictionService
    service: TenderService


def get_ctx(request: Request) -> Context:
    return request.app.state.ctx


def get_filters(
    q: str | None = Query(None, description="Free text: number, title, organizer, codes, address..."),
    status: str | None = Query(None, description="winner | predicted | not_predicted"),
    purchase_type: list[str] = Query(default=[], description="e.g. epNotificationEZK2020 (repeatable)"),
    responsible: str | None = Query(None, description="Organizer ID (top-level `responsible`)"),
    region: list[str] = Query(default=[], description="Region codes, e.g. 25 (repeatable)"),
    published_from: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}"),
    published_to: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}"),
    price_min: float | None = Query(None, ge=0),
    price_max: float | None = Query(None, ge=0),
    has_location: bool | None = Query(None),
    loc_key: str | None = Query(None, description="Map location key as returned by /api/map/points"),
) -> Filters:
    return Filters(
        q=(q or "").strip() or None,
        status=status if status in STATUSES else None,
        purchase_type=[t for t in purchase_type if t],
        responsible=(responsible or "").strip() or None,
        region=[r for r in region if r],
        published_from=published_from,
        published_to=published_to,
        price_min=price_min,
        price_max=price_max,
        has_location=has_location,
        loc_key=loc_key,
    )
