"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import meta, tenders
from app.api.deps import Context
from app.config import Settings
from app.logging_conf import setup_logging
from app.ml.predictor import PredictionService
from app.services.db import Database
from app.services.gosplan import GosplanClient
from app.services.tender_service import TenderService

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None, *, ctx: Context | None = None) -> FastAPI:
    """``ctx`` lets tests inject a mocked GosPlan client / predictor."""
    settings = settings or Settings.from_env()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        c = ctx
        if c is None:
            db = Database(settings.db_path)
            gosplan = GosplanClient(
                settings.gosplan_base_url, settings.gosplan_timeout, settings.gosplan_retries,
                settings.gosplan_backoff, settings.gosplan_concurrency,
                api_key=settings.gosplan_api_key,
            )
            predictor = PredictionService(settings.artifact_path)
            service = TenderService(db, gosplan, predictor, settings.max_batch_size)
            c = Context(settings, db, gosplan, predictor, service)
            if settings.model_autoload:
                predictor.start_loading()  # background: the API is usable immediately
        app.state.ctx = c
        log.info("started; DB=%s GosPlan=%s", settings.db_path, settings.gosplan_base_url)
        yield
        await c.gosplan.aclose()

    app = FastAPI(
        title="Tender Price Predictor",
        version="1.0.0",
        description="Predicts the final winning price of Russian public procurements (EF / EZK / EZT) at notice "
        "time and shows tenders on a map. Prediction logic is the unchanged trained model from model_train.ipynb.",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.include_router(tenders.router)
    app.include_router(meta.router)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):  # readable JSON instead of a stack trace
        log.exception("unhandled error")
        return JSONResponse({"detail": "Unexpected server error. Check the server log."}, status_code=500)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app


def app_factory() -> FastAPI:  # uvicorn --factory app.main:app_factory
    return create_app()
