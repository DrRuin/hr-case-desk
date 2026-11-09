"""Append-only case log and executed actions in SQLite, reached only through a tenant-scoped handle."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS events (
    tenant TEXT NOT NULL, case_id TEXT NOT NULL, seq INTEGER NOT NULL,
    at TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL,
    PRIMARY KEY (tenant, case_id, seq)
) STRICT, WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS effects (
    tenant TEXT NOT NULL, key TEXT NOT NULL, result TEXT NOT NULL,
    PRIMARY KEY (tenant, key)
) STRICT, WITHOUT ROWID;
"""


class Store:
    """The database; hand out `scoped` views, never raw queries."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        """Wrap an open connection."""
        self.db = db

    @classmethod
    async def open(cls, path: Path | str) -> "Store":
        """Connect and create the tables."""
        db = await aiosqlite.connect(path)
        await db.executescript(SCHEMA)
        await db.commit()
        return cls(db)

    def scoped(self, tenant: str) -> "CaseLog":
        """The log of one tenant."""
        return CaseLog(self.db, tenant)

    async def close(self) -> None:
        """Close the connection."""
        await self.db.close()


class CaseLog:
    """One tenant's cases: every query carries the tenant and no method accepts another."""

    def __init__(self, db: aiosqlite.Connection, tenant: str) -> None:
        """Bind the connection to a tenant."""
        self.db, self.tenant = db, tenant

    async def append(self, case: str, kind: str, body: dict[str, Any]) -> None:
        """Add an event at the end of a case's history; events are never updated or deleted."""
        await self.db.execute(
            "INSERT INTO events SELECT ?, ?, COALESCE(MAX(seq), 0) + 1, ?, ?, ? FROM events WHERE tenant = ? AND case_id = ?",
            (self.tenant, case, datetime.now(UTC).isoformat(), kind, json.dumps(body), self.tenant, case),
        )
        await self.db.commit()

    async def history(self, case: str) -> list[tuple[str, str, dict[str, Any]]]:
        """A case's events in order as (at, kind, body)."""
        rows = await self.db.execute_fetchall(
            "SELECT at, kind, body FROM events WHERE tenant = ? AND case_id = ? ORDER BY seq", (self.tenant, case)
        )
        return [(at, kind, json.loads(body)) for at, kind, body in rows]

    async def cases(self) -> list[str]:
        """Case ids, newest first."""
        rows = await self.db.execute_fetchall(
            "SELECT case_id FROM events WHERE tenant = ? GROUP BY case_id ORDER BY MIN(at) DESC", (self.tenant,)
        )
        return [case for (case,) in rows]

    async def effect(self, key: str) -> str | None:
        """The stored result of an action already run under this idempotency key."""
        rows = await self.db.execute_fetchall(
            "SELECT result FROM effects WHERE tenant = ? AND key = ?", (self.tenant, key)
        )
        return rows[0][0] if rows else None

    async def settle(self, key: str, result: str) -> str:
        """Record an action's result once in one statement; a later writer gets the first result back."""
        rows = await self.db.execute_fetchall(
            "INSERT INTO effects VALUES (?, ?, ?) ON CONFLICT (tenant, key) DO UPDATE SET result = result RETURNING result",
            (self.tenant, key, result),
        )
        await self.db.commit()
        return rows[0][0]
