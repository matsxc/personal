"""Tiny SQLite persistence layer.

The hub must survive a restart mid-incident, so every incident, acknowledgement,
delivery attempt and device heartbeat is written to disk immediately. SQLite is
enough: this system sees a handful of events per day, and one file is trivial to
back up.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    kind TEXT NOT NULL,            -- panic | test | offline
    opened_at REAL NOT NULL,
    acked_at REAL,
    resolved_at REAL,
    resolved_by TEXT,
    note TEXT,
    extra TEXT                     -- JSON blob from the device (battery, rssi, ...)
);
CREATE TABLE IF NOT EXISTS acks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    contact_id TEXT NOT NULL,
    at REAL NOT NULL,
    eta_minutes INTEGER,
    status TEXT NOT NULL,          -- seen | on_my_way | arrived | cannot_come
    note TEXT
);
CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT,
    step TEXT,
    contact_id TEXT NOT NULL,
    method TEXT NOT NULL,
    provider TEXT NOT NULL,
    at REAL NOT NULL,
    ok INTEGER NOT NULL,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    last_seen REAL,
    online INTEGER NOT NULL DEFAULT 1,
    extra TEXT
);
CREATE INDEX IF NOT EXISTS idx_acks_incident ON acks(incident_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_incident ON deliveries(incident_id);
"""


@dataclass
class Incident:
    id: str
    device_id: str
    kind: str
    opened_at: float
    acked_at: float | None
    resolved_at: float | None
    resolved_by: str | None
    note: str | None
    extra: dict[str, Any]

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None

    @property
    def is_acked(self) -> bool:
        return self.acked_at is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "kind": self.kind,
            "opened_at": self.opened_at,
            "acked_at": self.acked_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "note": self.note,
            "extra": self.extra,
        }


def _row_to_incident(row: sqlite3.Row) -> Incident:
    return Incident(
        id=row["id"],
        device_id=row["device_id"],
        kind=row["kind"],
        opened_at=row["opened_at"],
        acked_at=row["acked_at"],
        resolved_at=row["resolved_at"],
        resolved_by=row["resolved_by"],
        note=row["note"],
        extra=json.loads(row["extra"] or "{}"),
    )


class Database:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # -- incidents ---------------------------------------------------------
    def open_incident(self, device_id: str, kind: str, extra: dict[str, Any] | None = None) -> Incident:
        iid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO incidents (id, device_id, kind, opened_at, extra) VALUES (?,?,?,?,?)",
                (iid, device_id, kind, now, json.dumps(extra or {})),
            )
            self._conn.commit()
        return Incident(iid, device_id, kind, now, None, None, None, None, extra or {})

    def get_incident(self, iid: str) -> Incident | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
        return _row_to_incident(row) if row else None

    def open_incidents(self) -> list[Incident]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM incidents WHERE resolved_at IS NULL ORDER BY opened_at DESC"
            ).fetchall()
        return [_row_to_incident(r) for r in rows]

    def recent_incidents(self, limit: int = 50) -> list[Incident]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM incidents ORDER BY opened_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_incident(r) for r in rows]

    def latest_open_for_device(self, device_id: str, within_s: float) -> Incident | None:
        cutoff = time.time() - within_s
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM incidents WHERE device_id=? AND resolved_at IS NULL AND opened_at>=? "
                "ORDER BY opened_at DESC LIMIT 1",
                (device_id, cutoff),
            ).fetchone()
        return _row_to_incident(row) if row else None

    def ack_incident(
        self, iid: str, contact_id: str, status: str, eta_minutes: int | None, note: str | None
    ) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO acks (incident_id, contact_id, at, eta_minutes, status, note) VALUES (?,?,?,?,?,?)",
                (iid, contact_id, now, eta_minutes, status, note),
            )
            if status in ("on_my_way", "arrived"):
                self._conn.execute(
                    "UPDATE incidents SET acked_at=COALESCE(acked_at, ?) WHERE id=?", (now, iid)
                )
            self._conn.commit()

    def resolve_incident(self, iid: str, by: str, note: str | None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE incidents SET resolved_at=?, resolved_by=?, note=? WHERE id=? AND resolved_at IS NULL",
                (time.time(), by, note, iid),
            )
            self._conn.commit()

    def acks_for(self, iid: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM acks WHERE incident_id=? ORDER BY at", (iid,)
            ).fetchall()
        return [dict(r) for r in rows]

    def has_arrival(self, iid: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM acks WHERE incident_id=? AND status='arrived' LIMIT 1", (iid,)
            ).fetchone()
        return row is not None

    # -- deliveries ----------------------------------------------------------
    def log_delivery(
        self,
        incident_id: str | None,
        step: str | None,
        contact_id: str,
        method: str,
        provider: str,
        ok: bool,
        detail: str | None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO deliveries (incident_id, step, contact_id, method, provider, at, ok, detail) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (incident_id, step, contact_id, method, provider, time.time(), int(ok), detail),
            )
            self._conn.commit()

    def deliveries_for(self, iid: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM deliveries WHERE incident_id=? ORDER BY at", (iid,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -- devices -------------------------------------------------------------
    def heartbeat(self, device_id: str, extra: dict[str, Any] | None = None) -> bool:
        """Record a heartbeat. Returns True if the device was previously marked offline."""
        with self._lock:
            row = self._conn.execute("SELECT online FROM devices WHERE id=?", (device_id,)).fetchone()
            was_offline = bool(row) and not row["online"]
            self._conn.execute(
                "INSERT INTO devices (id, last_seen, online, extra) VALUES (?,?,1,?) "
                "ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen, online=1, extra=excluded.extra",
                (device_id, time.time(), json.dumps(extra or {})),
            )
            self._conn.commit()
        return was_offline

    def device_states(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM devices").fetchall()
        return {
            r["id"]: {"last_seen": r["last_seen"], "online": bool(r["online"]), "extra": json.loads(r["extra"] or "{}")}
            for r in rows
        }

    def mark_offline(self, device_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO devices (id, last_seen, online) VALUES (?,NULL,0) "
                "ON CONFLICT(id) DO UPDATE SET online=0",
                (device_id,),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
