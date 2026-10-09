"""Location resolution without any external geocoder.

What the GosPlan purchase response actually contains (inspected on a real record):
* NO coordinates anywhere.
* top-level ``region`` - integer subject code (``25`` = Primorsky Krai),
* top-level ``delivery_places`` / ``delivery_places_kladr`` - arrays (empty in the sample),
* free-text addresses nested in ``docs[*].source`` (delivery place, organizer address).

Resolution order:
1. exact coordinates if the record carries them (``latitude``/``longitude`` etc., top-level or
   inside ``delivery_places`` items) - precision "exact";
2. otherwise the centroid of the region identified by ``region`` from the bundled table -
   precision "region" (shown in the UI as *approximate location*);
3. otherwise no location (the tender stays searchable but is not drawn).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.util import to_float

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "regions.json"


@dataclass(frozen=True)
class Location:
    region_code: str | None
    region_name: str | None
    lat: float | None
    lon: float | None
    precision: str | None  # "exact" | "region" | None
    key: str | None

    @property
    def has_point(self) -> bool:
        return self.lat is not None and self.lon is not None


@lru_cache(maxsize=1)
def region_table() -> dict[str, dict[str, Any]]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def normalize_region_code(value: Any) -> str | None:
    """25 / "25" / "025"? -> "25"; None/garbage -> None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        n = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    if n <= 0 or n > 999:
        return None
    return f"{n:02d}"


def _valid_point(lat: float | None, lon: float | None) -> bool:
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0, 0)


def _coords_from(obj: Any) -> tuple[float, float] | None:
    if not isinstance(obj, dict):
        return None
    for lat_k, lon_k in (("latitude", "longitude"), ("lat", "lon"), ("lat", "lng"), ("lat", "long")):
        lat, lon = to_float(obj.get(lat_k)), to_float(obj.get(lon_k))
        if _valid_point(lat, lon):
            return lat, lon  # type: ignore[return-value]
    return None


def extract_exact_coords(response: dict[str, Any]) -> tuple[float, float] | None:
    """Look for coordinates at the top level or inside ``delivery_places`` items.

    The sample response has none, so this path is not exercised by real data yet; it is kept so
    that coordinates are used automatically if GosPlan starts returning them.
    """
    found = _coords_from(response)
    if found:
        return found
    places = response.get("delivery_places")
    if isinstance(places, list):
        for p in places:
            found = _coords_from(p)
            if found:
                return found
    return None


def region_name(code: str | None) -> str | None:
    if code is None:
        return None
    entry = region_table().get(code)
    return entry["name_en"] if entry else f"Region {code}"


def resolve(response: dict[str, Any]) -> Location:
    code = normalize_region_code(response.get("region"))
    name = region_name(code)
    exact = extract_exact_coords(response)
    if exact:
        lat, lon = exact
        return Location(code, name, lat, lon, "exact", f"pt:{lat:.4f},{lon:.4f}")
    entry = region_table().get(code) if code else None
    if entry:
        canon = entry.get("alias_of", code)
        return Location(code, name, entry["lat"], entry["lon"], "region", f"region:{canon}")
    return Location(code, name, None, None, None, None)
