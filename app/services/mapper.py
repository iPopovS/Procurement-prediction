"""GosPlan purchase response -> (model input ``raw``, display record).

``build_raw`` follows the mapping in the task description exactly (top-level fields only;
``responsible`` is the top-level value, counts come from the top-level lists), with ONE
deliberate difference: a missing ``object_info`` stays ``None`` instead of ``""``.
The training data contained nulls (never empty strings), and the pipeline computes
``txt_len = object_info.str.len()`` - ``""`` would produce 0 where training saw NaN, which
changes predictions (on the sample tender: median ratio 0.92 vs 0.90). The pipeline itself
applies ``fillna("")`` for the TF-IDF part, exactly as the notebook does.
"""

from __future__ import annotations

import re
from typing import Any

from app.ml.pipeline import RAW_COLS
from app.services import locations
from app.services.util import parse_dt, str_list, to_float
from app.services.winner import WinnerResult

PURCHASE_NUMBER_RE = re.compile(r"^\d{8,25}$")


def _s(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def build_raw(response: dict[str, Any]) -> dict[str, Any]:
    """The model's input row (RAW_COLS contract). Never reads ``docs`` or ``/protocols``."""
    pub = parse_dt(response.get("published_at"))
    col = parse_dt(response.get("collecting_finished_at"))
    ktru = response.get("ktru") or []
    okpd2 = response.get("okpd2") or []
    raw = {
        "purchase_number": _s(response.get("purchase_number")),
        "purchase_type": _s(response.get("purchase_type")),
        "responsible": _s(response.get("responsible")),
        "published_at_ts": pub.isoformat() if pub else None,
        "collecting_finished_at_ts": col.isoformat() if col else None,
        "max_price": to_float(response.get("max_price")),
        "contract_guarantee_part": to_float(response.get("contract_guarantee_part")),
        "ktru_cnt": len(ktru),
        "okpd2_cnt": len(okpd2),
        "position_numbers_cnt": len(response.get("position_numbers") or []),
        "object_info": _s(response.get("object_info")),
        "okpd2": str_list(okpd2),
        "ktru": str_list(ktru),
    }
    assert list(raw) == RAW_COLS
    return raw


# ---- display-only extras from the notice document embedded in ``docs`` ----------------------
def _dig(node: Any, *path: str) -> Any:
    for k in path:
        if not isinstance(node, dict):
            return None
        node = node.get(k)
    return node


def _collect(node: Any, key: str, out: list[str], depth: int = 0) -> None:
    if depth > 9 or len(out) >= 3:
        return
    if isinstance(node, dict):
        v = node.get(key)
        if isinstance(v, str) and v.strip() and v.strip() not in out:
            out.append(v.strip())
        for child in node.values():
            _collect(child, key, out, depth + 1)
    elif isinstance(node, list):
        for child in node:
            _collect(child, key, out, depth + 1)


def extract_extras(response: dict[str, Any]) -> dict[str, Any]:
    """Human-readable context from the notice document. All fields optional; defensive paths
    (only the EZK notice layout was inspected on a real record)."""
    notice = next(
        (d for d in (response.get("docs") or []) if isinstance(d, dict) and str(d.get("doc_type", "")).startswith("epNotification")),
        None,
    )
    src = (notice or {}).get("source") or {}
    org = _dig(src, "purchaseResponsibleInfo", "responsibleOrgInfo") or {}
    places: list[str] = []
    _collect(src, "deliveryPlace", places)
    if not places:
        _collect(src, "GARAddress", places)
    return {
        "placing_way": _s(_dig(src, "commonInfo", "placingWay", "name")),
        "etp": _s(_dig(src, "commonInfo", "ETP", "name")),
        "notice_url": _s(_dig(src, "commonInfo", "href")),
        "title_alt": _s(_dig(src, "commonInfo", "purchaseObjectInfo")),
        "responsible_name": _s(org.get("shortName")) or _s(org.get("fullName")),
        "responsible_full_name": _s(org.get("fullName")),
        "responsible_address": _s(org.get("postAddress")) or _s(org.get("factAddress")),
        "delivery_places_text": places,
    }


def _place_text(p: Any) -> str | None:
    if isinstance(p, str):
        return _s(p)
    if isinstance(p, dict):
        for k in ("address", "full_address", "name", "text", "place"):
            if _s(p.get(k)):
                return _s(p[k])
        vals = [v.strip() for v in p.values() if isinstance(v, str) and v.strip()]
        return ", ".join(vals[:3]) or None
    return None


def build_tender_record(response: dict[str, Any], winner: WinnerResult | None = None) -> dict[str, Any]:
    """Everything the repository stores for one tender."""
    raw = build_raw(response)
    extras = extract_extras(response)
    loc = locations.resolve(response)
    places = [t for t in (_place_text(p) for p in (response.get("delivery_places") or [])) if t]
    extras["delivery_places_text"] = places or extras["delivery_places_text"]

    gp = {k: v for k, v in response.items() if k != "docs"}  # docs can be tens of KB per tender
    gp["_extras"] = extras
    title = raw["object_info"] or extras["title_alt"]
    return {
        "purchase_number": raw["purchase_number"],
        "purchase_type": raw["purchase_type"],
        "responsible": raw["responsible"],
        "responsible_name": extras["responsible_name"],
        "title": title,
        "title_source": None if not title else ("object_info" if raw["object_info"] else "notice_document"),
        "object_info": raw["object_info"],
        "published_at": raw["published_at_ts"],
        "collecting_finished_at": raw["collecting_finished_at_ts"],
        "max_price": raw["max_price"],
        "contract_guarantee_part": raw["contract_guarantee_part"],
        "location": loc,
        "raw": raw,
        "gp": gp,
        "currency_code": _s(response.get("currency_code")),
        "winner": winner,
    }


def search_text(rec: dict[str, Any]) -> str:
    """Lower-cased haystack for LIKE search (SQLite's lower() is ASCII-only, so Python does it)."""
    gp = rec["gp"]
    ex = gp.get("_extras", {})
    parts = [
        rec["purchase_number"], rec["title"], rec["object_info"], rec["responsible"], rec["responsible_name"],
        rec["purchase_type"], rec["location"].region_name, ex.get("placing_way"),
        *(rec["raw"]["okpd2"]), *(rec["raw"]["ktru"]),
        *(gp.get("ikzs") or []), *(gp.get("plan_numbers") or []),
        *(ex.get("delivery_places_text") or []),
    ]
    return " ".join(str(p) for p in parts if p).casefold()
