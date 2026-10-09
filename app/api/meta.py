"""Health, config, filters, counters and map data."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query

from app.api.deps import Context, get_ctx, get_filters
from app.services.db import Filters
from app.services.locations import region_table

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", summary="Liveness + model state (always 200 while the process is up)")
async def health(ctx: Context = Depends(get_ctx)):
    return {"status": "ok", "model": ctx.predictor.status()}


@router.get("/config", summary="Frontend configuration (map tiles, limits)")
async def config(ctx: Context = Depends(get_ctx)):
    s = ctx.settings
    return {
        "tiles": {"url": s.map_tile_url or None, "attribution": s.map_tile_attribution, "max_zoom": s.map_tile_max_zoom},
        "max_batch_size": ctx.service.max_batch,
        "model": ctx.predictor.status(),
        "regions": {code: {"name_en": r["name_en"], "name_ru": r["name_ru"]} for code, r in region_table().items()},
    }


@router.get("/filters", summary="Available filter fields and values, generated from the stored data")
async def filters(ctx: Context = Depends(get_ctx)):
    return await asyncio.to_thread(ctx.db.facets)


@router.get("/filters/responsibles", summary="Autocomplete organizers (by name or ID)")
async def responsibles(q: str | None = Query(None), limit: int = Query(20, ge=1, le=100), ctx: Context = Depends(get_ctx)):
    return await asyncio.to_thread(ctx.db.responsibles, q, limit)


@router.get("/summary", summary="Counters for the current filters")
async def summary(f: Filters = Depends(get_filters), ctx: Context = Depends(get_ctx)):
    return await asyncio.to_thread(ctx.db.counts, f)


@router.get("/map/points", summary="Aggregated map points (GeoJSON), one feature per distinct location")
async def map_points(f: Filters = Depends(get_filters), ctx: Context = Depends(get_ctx)):
    groups = await asyncio.to_thread(ctx.db.map_groups, f)
    feats = []
    for g in groups:
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [g["lon"], g["lat"]]},
                "properties": {
                    "loc_key": g["loc_key"], "precision": g["loc_precision"], "region": g["region_name"],
                    "n": g["n"], "winner": g["n_winner"], "predicted": g["n_predicted"], "pending": g["n_pending"],
                    "ef": g["t_ef"], "ezk": g["t_ezk"], "ezt": g["t_ezt"], "total_max_price": g["total_max_price"],
                },
            }
        )
    return {"type": "FeatureCollection", "features": feats}
