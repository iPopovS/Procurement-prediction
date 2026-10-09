"""Pydantic models that document the public API (OpenAPI)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UploadRequest(BaseModel):
    purchase_numbers: list[str] = Field(default_factory=list, description="Purchase numbers to fetch from GosPlan.")
    records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Full GosPlan purchase records (the JSON of GET /fz44/purchases/{n}). A record may carry a "
        "top-level `winner_price`, which is stored for display (validated: 0 < price <= max_price).",
    )
    predict: bool = Field(False, description="Generate predictions immediately after storing.")
    fetch_winner: bool = Field(True, description="Look up the winner price in GosPlan protocols (display only).")
    skip_existing: bool = Field(False, description="Do not re-fetch purchase numbers that are already stored.")

    model_config = {
        "json_schema_extra": {
            "example": {"purchase_numbers": ["0320300101526000015"], "predict": True, "fetch_winner": True}
        }
    }


class PredictionBlock(BaseModel):
    status: str
    predicted_price: float | None = None
    expected_discount_pct: float | None = None
    warnings: list[str] = []
    reason: str | None = None


class ItemResult(BaseModel):
    purchase_number: str
    status: str = Field(description="created | updated | skipped | failed")
    error: str | None = None
    error_kind: str | None = None
    note: str | None = None
    winner_price: float | None = None
    winner_note: str | None = None
    prediction: PredictionBlock | None = None


class UploadSummary(BaseModel):
    requested: int
    created: int
    updated: int
    skipped: int
    failed: int
    with_winner_price: int
    predicted: int
    prediction_failed: int


class UploadResponse(BaseModel):
    summary: UploadSummary
    results: list[ItemResult]


class TenderSummary(BaseModel):
    purchase_number: str
    title: str | None
    title_source: str | None
    purchase_type: str | None
    type_label: str | None
    responsible: str | None
    responsible_name: str | None
    region_code: str | None
    region_name: str | None
    published_at: str | None
    collecting_finished_at: str | None
    max_price: float | None
    winner_price: float | None
    predicted_price: float | None
    expected_discount_pct: float | None
    status: str = Field(description="winner | predicted | pending (exclusive, used for colouring)")
    has_prediction: bool
    has_location: bool
    approximate_location: bool
    lat: float | None
    lon: float | None
    loc_precision: str | None
    loc_key: str | None


class TenderList(BaseModel):
    items: list[TenderSummary]
    total: int
    limit: int
    offset: int
