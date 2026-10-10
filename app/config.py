"""Configuration from environment variables (see .env.example). No secrets live in code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOSPLAN_TEST_URL = "https://v2test.gosplan.info"
GOSPLAN_PROD_URL = "https://v2.gosplan.info"


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or v.strip() == "" else v.strip()


def _bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    gosplan_base_url: str
    gosplan_timeout: float
    gosplan_retries: int
    gosplan_backoff: float
    gosplan_concurrency: int
    db_path: str
    artifact_path: str
    model_autoload: bool
    max_batch_size: int
    map_tile_url: str
    map_tile_attribution: str
    map_tile_max_zoom: int
    log_level: str
    gosplan_api_key: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        api_key = _env("GOSPLAN_API_KEY", "")
        # No key -> free test server; a key -> production server (an explicit GOSPLAN_BASE_URL still wins).
        default_url = GOSPLAN_PROD_URL if api_key else GOSPLAN_TEST_URL
        return cls(
            gosplan_api_key=api_key,
            gosplan_base_url=_env("GOSPLAN_BASE_URL", default_url).rstrip("/"),
            gosplan_timeout=float(_env("GOSPLAN_TIMEOUT", "20")),
            gosplan_retries=int(_env("GOSPLAN_RETRIES", "3")),
            gosplan_backoff=float(_env("GOSPLAN_BACKOFF", "0.5")),
            gosplan_concurrency=max(1, int(_env("GOSPLAN_CONCURRENCY", "8"))),
            db_path=_env("DB_PATH", str(ROOT / "data" / "tenders.db")),
            # folder downloaded from Hugging Face (or a legacy predictor.joblib file)
            artifact_path=_env("ARTIFACT_PATH", str(ROOT / "artifacts" / "hf_model")),
            model_autoload=_bool("MODEL_AUTOLOAD", True),
            max_batch_size=int(_env("MAX_BATCH_SIZE", "1000")),
            # Base-map tiles are optional. A variable that is SET but empty means "no tiles"
            # (borders only, fully offline); only an unset variable falls back to the default.
            map_tile_url=os.getenv("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png").strip(),
            map_tile_attribution=_env("MAP_TILE_ATTRIBUTION", "© OpenStreetMap contributors"),
            map_tile_max_zoom=int(_env("MAP_TILE_MAX_ZOOM", "18")),
            log_level=_env("LOG_LEVEL", "INFO").upper(),
        )
