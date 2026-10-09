"""SQLite persistence (WAL mode, one connection per thread).

Design notes
* Filtering, search and map aggregation are done in SQL so the UI stays fast with ~100k rows.
* ``search_text`` is a pre-lowercased haystack (Python ``casefold``) because SQLite's ``lower()``
  and ``LIKE`` are only case-insensitive for ASCII, and the data is Russian.
* ``status`` is a derived, exclusive state used for colouring: winner > predicted > pending.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ml.predictor import Prediction, type_label
from app.services.mapper import search_text
from app.services.winner import WinnerResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenders (
  purchase_number TEXT PRIMARY KEY,
  purchase_type TEXT, responsible TEXT, responsible_name TEXT,
  title TEXT, title_source TEXT, object_info TEXT,
  published_at TEXT, collecting_finished_at TEXT,
  max_price REAL, contract_guarantee_part REAL, currency_code TEXT,
  region_code TEXT, region_name TEXT,
  lat REAL, lon REAL, loc_precision TEXT, loc_key TEXT,
  winner_price REAL, winner_source TEXT, winner_published_at TEXT, winner_note TEXT,
  pred_ok INTEGER NOT NULL DEFAULT 0, pred_error TEXT, predicted_price REAL, predicted_price_sums REAL,
  ratio_median REAL, ratio_mean REAL, p_low REAL, p_nodrop REAL, predicted_at TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  search_text TEXT NOT NULL DEFAULT '', responsible_search TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
-- Large JSON documents live in a side table so that filter/search scans of `tenders` stay narrow.
CREATE TABLE IF NOT EXISTS blobs (
  purchase_number TEXT PRIMARY KEY,
  raw_json TEXT NOT NULL, gp_json TEXT NOT NULL, pred_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_t_status ON tenders(status);
CREATE INDEX IF NOT EXISTS ix_t_type ON tenders(purchase_type);
CREATE INDEX IF NOT EXISTS ix_t_region ON tenders(region_code);
CREATE INDEX IF NOT EXISTS ix_t_resp ON tenders(responsible);
CREATE INDEX IF NOT EXISTS ix_t_pub ON tenders(published_at);
CREATE INDEX IF NOT EXISTS ix_t_price ON tenders(max_price);
CREATE INDEX IF NOT EXISTS ix_t_loc ON tenders(loc_key);
"""

SORTS = {
    "published_desc": "published_at DESC, purchase_number DESC",
    "published_asc": "published_at ASC, purchase_number ASC",
    "price_desc": "max_price DESC, purchase_number DESC",
    "price_asc": "max_price ASC, purchase_number ASC",
}
STATUSES = {"winner", "predicted", "not_predicted"}


def _now() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def _esc(token: str) -> str:
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like(token: str) -> str:
    return "%" + _esc(token) + "%"


@dataclass
class Filters:
    q: str | None = None
    status: str | None = None  # winner | predicted | not_predicted
    purchase_type: list[str] = field(default_factory=list)
    responsible: str | None = None
    region: list[str] = field(default_factory=list)
    published_from: str | None = None  # YYYY-MM-DD
    published_to: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    has_location: bool | None = None
    loc_key: str | None = None

    def where(self) -> tuple[str, list[Any]]:
        cl: list[str] = []
        p: list[Any] = []
        if self.q:
            for tok in self.q.casefold().split():
                cl.append("search_text LIKE ? ESCAPE '\\'")
                p.append(_like(tok))
        if self.status == "winner":
            cl.append("winner_price IS NOT NULL")
        elif self.status == "predicted":
            cl.append("pred_ok = 1")
        elif self.status == "not_predicted":
            cl.append("pred_ok = 0")
        if self.purchase_type:
            cl.append(f"purchase_type IN ({','.join('?' * len(self.purchase_type))})")
            p += self.purchase_type
        if self.responsible:
            cl.append("responsible = ?")
            p.append(self.responsible)
        if self.region:
            cl.append(f"region_code IN ({','.join('?' * len(self.region))})")
            p += self.region
        if self.published_from:
            cl.append("published_at >= ?")
            p.append(self.published_from)
        if self.published_to:
            cl.append("published_at <= ?")
            p.append(self.published_to + "T23:59:59.999999" if len(self.published_to) == 10 else self.published_to)
        if self.price_min is not None:
            cl.append("max_price >= ?")
            p.append(self.price_min)
        if self.price_max is not None:
            cl.append("max_price <= ?")
            p.append(self.price_max)
        if self.has_location is True:
            cl.append("lat IS NOT NULL")
        elif self.has_location is False:
            cl.append("lat IS NULL")
        if self.loc_key:
            cl.append("loc_key = ?")
            p.append(self.loc_key)
        return (" AND ".join(cl) if cl else "1=1"), p


SUMMARY_COLS = (
    "purchase_number, title, title_source, purchase_type, responsible, responsible_name, region_code, region_name, "
    "published_at, collecting_finished_at, max_price, winner_price, predicted_price, pred_ok, status, "
    "lat, lon, loc_precision, loc_key"
)


SUMMARY_KEYS = [c.strip() for c in SUMMARY_COLS.split(",")]


def _summary(r: sqlite3.Row) -> dict[str, Any]:
    """Row (partial or full) -> JSON-ready summary dict used by lists, search and the map."""
    d = {k: r[k] for k in SUMMARY_KEYS}
    d["type_label"] = type_label(d["purchase_type"])
    d["has_location"] = d["lat"] is not None
    d["approximate_location"] = d["loc_precision"] == "region"
    d["has_prediction"] = bool(d.pop("pred_ok"))
    mp, pp = d["max_price"], d["predicted_price"]
    d["expected_discount_pct"] = (1 - pp / mp) * 100 if (mp and pp is not None) else None
    return d


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._shared: sqlite3.Connection | None = None
        if path == ":memory:":  # tests: one shared connection (guarded by a lock)
            self._shared = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared.row_factory = sqlite3.Row
            self._mem_lock = threading.RLock()
        self._conn().executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        if self._shared is not None:
            return self._shared
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=15, isolation_level=None)  # autocommit; explicit BEGIN below
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA busy_timeout=15000")
            self._local.conn = c
        return c

    # -- small helpers ----------------------------------------------------------------
    def _run(self, sql: str, params: list[Any] | tuple = ()) -> list[sqlite3.Row]:
        if self._shared is not None:
            with self._mem_lock:
                return self._shared.execute(sql, params).fetchall()
        return self._conn().execute(sql, params).fetchall()

    def _tx(self, fn):
        if self._shared is not None:
            with self._mem_lock:
                try:
                    out = fn(self._shared)
                    self._shared.commit()
                    return out
                except Exception:
                    self._shared.rollback()
                    raise
        c = self._conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            out = fn(c)
        except Exception:
            c.execute("ROLLBACK")
            raise
        c.execute("COMMIT")
        return out

    # -- writes -------------------------------------------------------------------------
    def exists_many(self, numbers: list[str]) -> set[str]:
        found: set[str] = set()
        for i in range(0, len(numbers), 500):
            part = numbers[i : i + 500]
            rows = self._run(f"SELECT purchase_number FROM tenders WHERE purchase_number IN ({','.join('?' * len(part))})", part)
            found.update(r[0] for r in rows)
        return found

    def upsert_many(self, records: list[dict[str, Any]]) -> dict[str, str]:
        """Insert/update tenders. Returns {purchase_number: 'created'|'updated'}.

        An update keeps the stored prediction only when the model input is unchanged, and keeps
        the stored winner unless a new valid one is supplied.
        """

        def work(c: sqlite3.Connection) -> dict[str, str]:
            res: dict[str, str] = {}
            now = _now()
            for rec in records:
                pn = rec["purchase_number"]
                loc = rec["location"]
                raw_json = json.dumps(rec["raw"], ensure_ascii=False, sort_keys=True)
                gp_json = json.dumps(rec["gp"], ensure_ascii=False)
                w: WinnerResult | None = rec.get("winner")
                prev = c.execute(
                    "SELECT b.raw_json, b.pred_json, t.winner_price, t.winner_source, t.winner_published_at, t.winner_note,"
                    " t.pred_ok, t.pred_error, t.predicted_price, t.predicted_price_sums, t.ratio_median, t.ratio_mean,"
                    " t.p_low, t.p_nodrop, t.predicted_at, t.created_at FROM tenders t JOIN blobs b USING (purchase_number)"
                    " WHERE t.purchase_number=?",
                    (pn,),
                ).fetchone()
                cols = {
                    "purchase_number": pn, "purchase_type": rec["purchase_type"], "responsible": rec["responsible"],
                    "responsible_name": rec["responsible_name"], "title": rec["title"], "title_source": rec["title_source"],
                    "object_info": rec["object_info"], "published_at": rec["published_at"],
                    "collecting_finished_at": rec["collecting_finished_at"], "max_price": rec["max_price"],
                    "contract_guarantee_part": rec["contract_guarantee_part"], "currency_code": rec.get("currency_code"),
                    "region_code": loc.region_code, "region_name": loc.region_name, "lat": loc.lat, "lon": loc.lon,
                    "loc_precision": loc.precision, "loc_key": loc.key,
                    "search_text": search_text(rec),
                    "responsible_search": f"{rec['responsible'] or ''} {rec['responsible_name'] or ''}".casefold(),
                    "updated_at": now,
                }
                # winner: new valid value wins, otherwise keep what we had
                if w is not None and w.price is not None:
                    cols.update(winner_price=w.price, winner_source=w.source, winner_published_at=w.published_at, winner_note=w.note)
                elif prev is not None:
                    cols.update(winner_price=prev["winner_price"], winner_source=prev["winner_source"],
                                winner_published_at=prev["winner_published_at"], winner_note=prev["winner_note"])
                else:
                    cols.update(winner_price=None, winner_source=None, winner_published_at=None,
                                winner_note=w.note if w is not None else None)
                # prediction: keep only if the model input did not change
                keep_pred = prev is not None and prev["raw_json"] == raw_json
                for k in ("pred_ok", "pred_error", "predicted_price", "predicted_price_sums", "ratio_median",
                          "ratio_mean", "p_low", "p_nodrop", "predicted_at"):
                    cols[k] = prev[k] if keep_pred else (0 if k == "pred_ok" else None)
                pred_json = prev["pred_json"] if keep_pred else None
                cols["status"] = "winner" if cols["winner_price"] is not None else ("predicted" if cols["pred_ok"] else "pending")
                cols["created_at"] = prev["created_at"] if prev else now
                names = list(cols)
                c.execute(
                    f"INSERT OR REPLACE INTO tenders ({','.join(names)}) VALUES ({','.join('?' * len(names))})",
                    [cols[n] for n in names],
                )
                c.execute(
                    "INSERT OR REPLACE INTO blobs (purchase_number, raw_json, gp_json, pred_json) VALUES (?,?,?,?)",
                    (pn, raw_json, gp_json, pred_json),
                )
                res[pn] = "updated" if prev else "created"
            return res

        return self._tx(work)

    def set_predictions(self, items: list[tuple[str, Prediction]]) -> None:
        def work(c: sqlite3.Connection) -> None:
            now = _now()
            for pn, pred in items:
                if pred.ok and pred.result:
                    r = pred.result
                    c.execute(
                        "UPDATE tenders SET pred_ok=1, pred_error=NULL, predicted_price=?, predicted_price_sums=?,"
                        " ratio_median=?, ratio_mean=?, p_low=?, p_nodrop=?, predicted_at=?, updated_at=?,"
                        " status=CASE WHEN winner_price IS NOT NULL THEN 'winner' ELSE 'predicted' END"
                        " WHERE purchase_number=?",
                        (r["predicted_price"], r["predicted_price_for_sums"], r["ratio_median"], r["ratio_mean"],
                         r["p_low"], r["p_nodrop"], now, now, pn),
                    )
                    c.execute("UPDATE blobs SET pred_json=? WHERE purchase_number=?", (json.dumps(r), pn))
                else:
                    c.execute(
                        "UPDATE tenders SET pred_ok=0, pred_error=?, predicted_price=NULL, predicted_price_sums=NULL,"
                        " ratio_median=NULL, ratio_mean=NULL, p_low=NULL, p_nodrop=NULL, predicted_at=?,"
                        " updated_at=?, status=CASE WHEN winner_price IS NOT NULL THEN 'winner' ELSE 'pending' END"
                        " WHERE purchase_number=?",
                        (pred.reason, now, now, pn),
                    )
                    c.execute("UPDATE blobs SET pred_json=NULL WHERE purchase_number=?", (pn,))

        self._tx(work)

    def set_winner(self, pn: str, w: WinnerResult) -> None:
        def work(c: sqlite3.Connection) -> None:
            if w.price is not None:
                c.execute(
                    "UPDATE tenders SET winner_price=?, winner_source=?, winner_published_at=?, winner_note=?, status='winner',"
                    " updated_at=? WHERE purchase_number=?",
                    (w.price, w.source, w.published_at, w.note, _now(), pn),
                )
            else:
                c.execute(
                    "UPDATE tenders SET winner_price=NULL, winner_source=NULL, winner_published_at=NULL, winner_note=?,"
                    " status=CASE WHEN pred_ok=1 THEN 'predicted' ELSE 'pending' END, updated_at=? WHERE purchase_number=?",
                    (w.note, _now(), pn),
                )

        self._tx(work)

    def delete(self, pn: str) -> bool:
        def work(c: sqlite3.Connection) -> bool:
            c.execute("DELETE FROM blobs WHERE purchase_number=?", (pn,))
            return c.execute("DELETE FROM tenders WHERE purchase_number=?", (pn,)).rowcount > 0

        return self._tx(work)

    # -- reads --------------------------------------------------------------------------
    def get_raw(self, pn: str) -> dict[str, Any] | None:
        rows = self._run(
            "SELECT b.raw_json, t.currency_code FROM tenders t JOIN blobs b USING (purchase_number) WHERE t.purchase_number=?", (pn,)
        )
        if not rows:
            return None
        raw = json.loads(rows[0]["raw_json"])
        raw["currency_code"] = rows[0]["currency_code"]
        return raw

    def get(self, pn: str) -> dict[str, Any] | None:
        rows = self._run(
            "SELECT t.*, b.raw_json, b.gp_json, b.pred_json FROM tenders t JOIN blobs b USING (purchase_number)"
            " WHERE t.purchase_number=?",
            (pn,),
        )
        if not rows:
            return None
        r = rows[0]
        d = _summary(r)
        gp = json.loads(r["gp_json"])
        d["extras"] = gp.pop("_extras", {})
        d["gosplan"] = gp
        d["raw"] = json.loads(r["raw_json"])
        d["contract_guarantee_part"] = r["contract_guarantee_part"]
        d["currency_code"] = r["currency_code"]
        d["created_at"], d["updated_at"] = r["created_at"], r["updated_at"]
        d["prediction"] = {
            "available": bool(r["pred_ok"]),
            "error": r["pred_error"],
            "predicted_at": r["predicted_at"],
            **(json.loads(r["pred_json"]) if r["pred_json"] else {}),
        }
        d["winner"] = {
            "price": r["winner_price"], "source": r["winner_source"],
            "published_at": r["winner_published_at"], "note": r["winner_note"],
        }
        if r["winner_price"] is not None and r["predicted_price"] is not None:
            diff = r["predicted_price"] - r["winner_price"]
            d["prediction_error"] = {
                "abs": diff,
                "pct_of_winner": diff / r["winner_price"] * 100,
                "pct_of_max_price": diff / r["max_price"] * 100 if r["max_price"] else None,
            }
        else:
            d["prediction_error"] = None
        return d

    def query(self, f: Filters, limit: int, offset: int, sort: str = "published_desc") -> tuple[list[dict[str, Any]], int]:
        where, params = f.where()
        total = self._run(f"SELECT COUNT(*) FROM tenders WHERE {where}", params)[0][0]
        order = SORTS.get(sort, SORTS["published_desc"])
        args = list(params)
        if f.q and f.q.strip():  # purchase numbers that start with the query come first
            order = "(purchase_number LIKE ? ESCAPE '\\') DESC, " + order
            args.append(_esc(f.q.strip().casefold()) + "%")
        rows = self._run(
            f"SELECT {SUMMARY_COLS} FROM tenders WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
            [*args, limit, offset],
        )
        return [_summary(r) for r in rows], total

    def counts(self, f: Filters) -> dict[str, int]:
        where, params = f.where()
        r = self._run(
            "SELECT COUNT(*) n, COALESCE(SUM(status='winner'),0) winner, COALESCE(SUM(status='predicted'),0) predicted,"
            " COALESCE(SUM(status='pending'),0) pending, COALESCE(SUM(lat IS NOT NULL),0) located,"
            " COALESCE(SUM(winner_price IS NOT NULL),0) with_winner, COALESCE(SUM(pred_ok),0) with_prediction,"
            f" COALESCE(SUM(max_price),0) total_max_price FROM tenders WHERE {where}",
            params,
        )[0]
        d = {k: r[k] for k in r.keys()}  # noqa: SIM118 - sqlite3.Row has no .items()
        d["unlocated"] = d["n"] - d["located"]
        return d

    def map_groups(self, f: Filters) -> list[dict[str, Any]]:
        """One row per distinct location with counts per status and per purchase type.

        (Sample titles for the hover tooltip are fetched lazily from the list endpoint.)
        """
        where, params = f.where()
        rows = self._run(
            "SELECT loc_key, lat, lon, loc_precision, MIN(region_name) region_name, COUNT(*) n,"
            " SUM(status='winner') n_winner, SUM(status='predicted') n_predicted, SUM(status='pending') n_pending,"
            " SUM(purchase_type='epNotificationEF2020') t_ef, SUM(purchase_type='epNotificationEZK2020') t_ezk,"
            " SUM(purchase_type='epNotificationEZT2020') t_ezt, SUM(max_price) total_max_price"
            f" FROM tenders WHERE lat IS NOT NULL AND {where} GROUP BY loc_key",
            params,
        )
        out = []
        for r in rows:
            out.append({k: r[k] for k in r.keys()})  # noqa: SIM118 - sqlite3.Row has no .items()
        return out

    def facets(self) -> dict[str, Any]:
        types = [
            {"value": r[0], "label": type_label(r[0]), "count": r[1]}
            for r in self._run("SELECT purchase_type, COUNT(*) FROM tenders GROUP BY 1 ORDER BY 2 DESC")
        ]
        regions = [
            {"value": r[0], "label": r[1] or f"Region {r[0]}", "count": r[2]}
            for r in self._run(
                "SELECT region_code, MIN(region_name), COUNT(*) FROM tenders WHERE region_code IS NOT NULL"
                " GROUP BY 1 ORDER BY 3 DESC"
            )
        ]
        no_region = self._run("SELECT COUNT(*) FROM tenders WHERE region_code IS NULL")[0][0]
        st = self._run(
            "SELECT COUNT(*), COALESCE(SUM(winner_price IS NOT NULL),0), COALESCE(SUM(pred_ok),0), MIN(published_at),"
            " MAX(published_at), MIN(max_price), MAX(max_price) FROM tenders"
        )[0]
        total, n_win, n_pred = st[0], st[1], st[2]
        return {
            "total": total,
            "status": [
                {"value": "winner", "label": "Has winner price", "count": n_win},
                {"value": "predicted", "label": "Has prediction", "count": n_pred},
                {"value": "not_predicted", "label": "No prediction yet", "count": total - n_pred},
            ],
            "purchase_type": types,
            "region": regions,
            "region_unknown_count": no_region,
            "published_range": {"min": st[3], "max": st[4]},
            "price_range": {"min": st[5], "max": st[6]},
            "responsible": {"search_endpoint": "/api/filters/responsibles?q={text}"},
        }

    def responsibles(self, q: str | None, limit: int = 20) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = "responsible IS NOT NULL"
        for tok in (q or "").casefold().split():
            where += " AND responsible_search LIKE ? ESCAPE '\\'"
            params.append(_like(tok))
        rows = self._run(
            f"SELECT responsible, MAX(responsible_name) name, COUNT(*) n FROM tenders WHERE {where}"
            " GROUP BY responsible ORDER BY n DESC LIMIT ?",
            [*params, limit],
        )
        return [{"value": r["responsible"], "label": r["name"] or r["responsible"], "count": r["n"]} for r in rows]

    def db_size(self) -> int | None:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return None
