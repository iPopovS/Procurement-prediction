"""Winner-price extraction from GosPlan protocols (DISPLAY ONLY - never a model input).

Verified on a real record (``docs[]`` of purchase 0320300101526000015, which has the same shape
as the ``/protocols`` items): for ``epProtocolEZK2020Final`` the applications live at
``source.protocolInfo.applicationsInfo.applicationInfo`` (list or single dict), each with
``finalPrice`` and ``admittedInfo.appAdmittedInfo.appRating``. The winner is the application
with the LOWEST numeric ``appRating``.

NOT verified against real data (only specified in the task, the training notebook reads a
pre-built table and does not contain the extraction): the EF and EZT field paths below. They
follow the task description; EZT falls back through the generic price fields. If a real EZT or
EF protocol differs, adjust ``PRICE_PATHS`` - everything else stays the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.util import to_float

# protocol type -> ordered candidate paths (relative to one application node)
PRICE_PATHS: dict[str, list[tuple[str, ...]]] = {
    "epProtocolEZK2020Final": [("finalPrice",)],
    "epProtocolEF2020Final": [("finalPrice",), ("lastPriceOffer", "price")],
    "epProtocolEZT2020Final": [("finalPrice",), ("lastPriceOffer", "price"), ("priceOffer", "price")],  # unverified
    "epProtocolEF2020SubmitOffers": [("priceOffer", "price")],
}
# Final protocols first; the EF submit-offers protocol is a preliminary stage -> last resort.
PRIORITY = [
    "epProtocolEZK2020Final",
    "epProtocolEF2020Final",
    "epProtocolEZT2020Final",
    "epProtocolEF2020SubmitOffers",
]
RATING_PATH = ("admittedInfo", "appAdmittedInfo", "appRating")


@dataclass
class WinnerResult:
    price: float | None = None
    source: str | None = None  # protocol doc_type the price came from
    published_at: str | None = None
    note: str | None = None  # why missing / caveats (internal, shown only as a hint)


def _get(node: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _as_list(v: Any) -> list[Any]:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _find_key(node: Any, key: str, depth: int = 0) -> Any:
    """Bounded recursive search for the first occurrence of ``key`` (fallback for odd shapes)."""
    if depth > 6:
        return None
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for v in node.values():
            r = _find_key(v, key, depth + 1)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = _find_key(v, key, depth + 1)
            if r is not None:
                return r
    return None


def _applications(source: Any) -> list[dict[str, Any]]:
    apps = _get(source, ("protocolInfo", "applicationsInfo", "applicationInfo"))
    if apps is None:
        apps = _find_key(_get(source, ("protocolInfo",)) or {}, "applicationInfo")
    return [a for a in _as_list(apps) if isinstance(a, dict)]


def _app_price(app: dict[str, Any], paths: list[tuple[str, ...]]) -> float | None:
    for path in paths:
        price = to_float(_get(app, path))
        if price is not None and price > 0:
            return price
    return None


def _pick_winner_price(source: Any, doc_type: str) -> tuple[float | None, str | None]:
    apps = _applications(source)
    if not apps:
        return None, "protocol has no applications"
    paths = PRICE_PATHS[doc_type]
    rated: list[tuple[float, dict[str, Any]]] = []
    for a in apps:
        rating = to_float(_get(a, RATING_PATH))
        if rating is not None:
            rated.append((rating, a))
    if rated:
        rated.sort(key=lambda t: t[0])  # lowest numeric appRating wins
        return _app_price(rated[0][1], paths), None
    # No ratings at all: only unambiguous cases are accepted.
    if len(apps) == 1:
        return _app_price(apps[0], paths), "single application without rating"
    prices = [p for p in (_app_price(a, paths) for a in apps) if p is not None]
    if prices:
        return min(prices), "no application ratings; lowest price used"
    return None, None


def validate_price(price: float | None, max_price: float | None) -> tuple[float | None, str | None]:
    """winner_price must satisfy 0 < price <= max_price, otherwise it is treated as missing."""
    if price is None:
        return None, None
    if max_price is None:
        return None, "max_price unknown; winner price cannot be validated"
    if price <= 0:
        return None, f"winner price {price:g} is not positive"
    if price > max_price + 1e-6:
        return None, f"winner price {price:,.2f} exceeds max price {max_price:,.2f}"
    return price, None


def extract_winner_price(protocols: Any, max_price: float | None) -> WinnerResult:
    """Pick the winner price from a list of protocol documents (``/protocols`` response)."""
    if not isinstance(protocols, list) or not protocols:
        return WinnerResult(note="no protocols published yet")
    by_type: dict[str, list[dict[str, Any]]] = {}
    for p in protocols:
        if isinstance(p, dict) and p.get("doc_type") in PRICE_PATHS:
            by_type.setdefault(p["doc_type"], []).append(p)
    if not by_type:
        return WinnerResult(note="no results protocol among the published documents")

    notes: list[str] = []
    for doc_type in PRIORITY:
        docs = sorted(by_type.get(doc_type, []), key=lambda d: str(d.get("published_at") or ""), reverse=True)
        for doc in docs:  # newest version first
            price, note = _pick_winner_price(doc.get("source"), doc_type)
            valid, problem = validate_price(price, max_price)
            if valid is not None:
                caveat = "; ".join(x for x in (note,) if x) or None
                if doc_type == "epProtocolEF2020SubmitOffers":
                    caveat = "preliminary: taken from the submit-offers protocol" + (f"; {caveat}" if caveat else "")
                return WinnerResult(valid, doc_type, doc.get("published_at"), caveat)
            if problem:
                notes.append(f"{doc_type}: {problem}")
            elif note:
                notes.append(f"{doc_type}: {note}")
    return WinnerResult(note="; ".join(notes) or "no valid winner price found")
