"""SQLite access for SoloPilot.

Reuses the 8 tables created by the existing Prisma migration verbatim. Only
three additive tables are introduced (price_item / ChatSession / ToolInvocation),
each required by a new requirement (DB-backed pricing, conversation state,
idempotency). No existing table or column is altered.

Prisma stores DateTime columns as INTEGER epoch milliseconds, so all timestamp
reads/writes here use that representation.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str = "c") -> str:
    return prefix + uuid.uuid4().hex


def iso_to_ms(value: str) -> int:
    """Parse an ISO-8601 string into epoch milliseconds."""
    from datetime import datetime

    text = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        # Treat naive input as local time; tests always pass an explicit offset.
        dt = dt.astimezone()
    return int(dt.timestamp() * 1000)


def ms_to_iso(value: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE so conflict checks and inserts are atomic."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS "price_item" (
                "id" TEXT NOT NULL PRIMARY KEY,
                "packageType" TEXT NOT NULL UNIQUE,
                "name" TEXT NOT NULL,
                "unitPriceCents" INTEGER NOT NULL,
                "sessionsPerUnit" INTEGER NOT NULL,
                "currency" TEXT NOT NULL DEFAULT 'CNY',
                "updatedAt" INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS "ChatSession" (
                "id" TEXT NOT NULL PRIMARY KEY,
                "leadId" TEXT NOT NULL,
                "stateJson" TEXT NOT NULL,
                "turnCount" INTEGER NOT NULL DEFAULT 0,
                "createdAt" INTEGER NOT NULL,
                "updatedAt" INTEGER NOT NULL,
                CONSTRAINT "ChatSession_leadId_fkey"
                    FOREIGN KEY ("leadId") REFERENCES "Lead" ("id")
                    ON DELETE CASCADE ON UPDATE CASCADE
            );

            CREATE TABLE IF NOT EXISTS "ToolInvocation" (
                "id" TEXT NOT NULL PRIMARY KEY,
                "sessionId" TEXT NOT NULL,
                "callKey" TEXT NOT NULL UNIQUE,
                "toolName" TEXT NOT NULL,
                "inputJson" TEXT NOT NULL,
                "outputJson" TEXT NOT NULL,
                "createdAt" INTEGER NOT NULL
            );
            """
        )
        seed_prices(conn)


def seed_prices(conn: sqlite3.Connection) -> None:
    """Idempotent: keep DB prices as the single source of truth for amounts."""
    rows = [
        ("single", "单节课", settings.PRICE_SINGLE_CENTS, 1),
        ("package4", "四节套餐", settings.PRICE_PACKAGE4_CENTS, settings.PACKAGE_SESSIONS),
    ]
    for package_type, name, cents, sessions in rows:
        conn.execute(
            """
            INSERT INTO "price_item"
                ("id", "packageType", "name", "unitPriceCents", "sessionsPerUnit", "currency", "updatedAt")
            VALUES (?, ?, ?, ?, ?, 'CNY', ?)
            ON CONFLICT("packageType") DO UPDATE SET
                "name" = excluded."name",
                "unitPriceCents" = excluded."unitPriceCents",
                "sessionsPerUnit" = excluded."sessionsPerUnit",
                "updatedAt" = excluded."updatedAt"
            """,
            (new_id("p"), package_type, name, cents, sessions, now_ms()),
        )


def get_price(conn: sqlite3.Connection, package_type: str) -> dict[str, Any] | None:
    row = conn.execute(
        'SELECT * FROM "price_item" WHERE "packageType" = ?', (package_type,)
    ).fetchone()
    return dict(row) if row else None


def list_prices(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute('SELECT * FROM "price_item" ORDER BY "packageType"')]


# ---------------------------------------------------------------- sessions
def get_session(conn: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    row = conn.execute('SELECT * FROM "ChatSession" WHERE "id" = ?', (session_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["state"] = json.loads(result["stateJson"])
    return result


def create_session(conn: sqlite3.Connection, lead_id: str) -> dict[str, Any]:
    session_id = new_id("s")
    state = {"stage": "greet", "pendingConfirmation": None, "confirmations": {}}
    conn.execute(
        'INSERT INTO "ChatSession" ("id","leadId","stateJson","turnCount","createdAt","updatedAt") '
        "VALUES (?,?,?,?,?,?)",
        (session_id, lead_id, json.dumps(state, ensure_ascii=False), 0, now_ms(), now_ms()),
    )
    return {"id": session_id, "leadId": lead_id, "state": state, "turnCount": 0}


def save_session(conn: sqlite3.Connection, session_id: str, state: dict[str, Any]) -> None:
    conn.execute(
        'UPDATE "ChatSession" SET "stateJson" = ?, "updatedAt" = ? WHERE "id" = ?',
        (json.dumps(state, ensure_ascii=False), now_ms(), session_id),
    )


def bump_turn(conn: sqlite3.Connection, session_id: str) -> int:
    conn.execute(
        'UPDATE "ChatSession" SET "turnCount" = "turnCount" + 1, "updatedAt" = ? WHERE "id" = ?',
        (now_ms(), session_id),
    )
    row = conn.execute(
        'SELECT "turnCount" FROM "ChatSession" WHERE "id" = ?', (session_id,)
    ).fetchone()
    return int(row[0])


# ---------------------------------------------------------------- idempotency
def lookup_invocation(conn: sqlite3.Connection, call_key: str) -> dict[str, Any] | None:
    row = conn.execute(
        'SELECT * FROM "ToolInvocation" WHERE "callKey" = ?', (call_key,)
    ).fetchone()
    return dict(row) if row else None


def store_invocation(
    conn: sqlite3.Connection, session_id: str, call_key: str, tool_name: str, args: dict, result: dict
) -> None:
    conn.execute(
        'INSERT OR IGNORE INTO "ToolInvocation" '
        '("id","sessionId","callKey","toolName","inputJson","outputJson","createdAt") '
        "VALUES (?,?,?,?,?,?,?)",
        (
            new_id("t"),
            session_id,
            call_key,
            tool_name,
            json.dumps(args, ensure_ascii=False),
            json.dumps(result, ensure_ascii=False),
            now_ms(),
        ),
    )
