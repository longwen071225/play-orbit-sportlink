"""Test harness.

Environment must be set BEFORE importing backend.config, because Settings is
instantiated at module import time. A fresh SQLite file is built from the
committed Prisma migration SQL, so tests exercise the real existing schema.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Allows running pytest from outside the project root (e.g. the workspace root
# delegates here via its pytest.ini). Harmless when already running in-tree.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TEST_DB = os.environ.get("SOLOPILOT_TEST_DB", str(ROOT / "prisma" / "solopilot_test.db"))
MIGRATION_SQL = ROOT / "prisma" / "migrations" / "20261106084617_init" / "migration.sql"

os.environ["SOLOPILOT_DATABASE_PATH"] = TEST_DB
os.environ.setdefault("SOLOPILOT_LLM_MODE", "mock")
os.environ.setdefault("SOLOPILOT_DASHSCOPE_API_KEY", "")
os.environ.setdefault("SOLOPILOT_DASHSCOPE_MODEL", "qwen3.7-plus")
os.environ.setdefault("SOLOPILOT_DASHSCOPE_FALLBACK_MODEL", "qwen3.8-max")
os.environ["SOLOPILOT_FORCE_STATE_MACHINE"] = "false"
os.environ["SOLOPILOT_MAX_TOOL_ROUNDS"] = "6"

from backend import db  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.llm import BailianClient  # noqa: E402

TABLES = [
    "AgentAction", "ToolInvocation", "AgentRun", "QuoteItem", "Quote",
    "Booking", "TrainingPlan", "Message", "ChatSession", "Lead",
]


def _build_schema() -> None:
    path = Path(TEST_DB)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(TEST_DB)
    conn.executescript(MIGRATION_SQL.read_text(encoding="utf-8"))
    conn.close()
    db.init_db()  # adds price_item / ChatSession / ToolInvocation and seeds prices


@pytest.fixture(scope="session", autouse=True)
def _schema():
    _build_schema()
    yield


@pytest.fixture(autouse=True)
def _clean_rows():
    with db.get_conn() as conn:
        for table in TABLES:
            conn.execute(f'DELETE FROM "{table}"')
        db.seed_prices(conn)
    yield


@pytest.fixture()
def raw():
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture()
def make_app():
    from backend.app import create_app
    from fastapi.testclient import TestClient

    def build(force_state_machine: bool = False, llm_mode: str = "mock", **overrides):
        cfg = Settings(
            LLM_MODE=llm_mode,
            DASHSCOPE_API_KEY="",
            DASHSCOPE_MODEL="qwen3.7-plus",
            DASHSCOPE_FALLBACK_MODEL="qwen3.8-max",
            DATABASE_PATH=TEST_DB,
            FORCE_STATE_MACHINE=force_state_machine,
            MAX_TOOL_ROUNDS=6,
            **overrides,
        )
        llm = BailianClient(cfg)
        llm.probe()
        app = create_app(llm)
        return TestClient(app), llm

    return build


@pytest.fixture()
def client(make_app):
    test_client, _ = make_app()
    with test_client as c:
        yield c
