"""StarFit: additive platform module mounted on the EXISTING FastAPI app.

No second server, no second database. register_starfit() is called once from
backend.app.create_app(); it creates missing sf_* tables, seeds demo data when
enabled, and includes the new router. Existing /api/v1/* routes are untouched.
"""
from __future__ import annotations

from typing import Any


def register_starfit(app: Any) -> None:
    from .. import db
    from ..config import settings
    from . import coachapi, portal
    from .schema import ensure_schema
    from .seed import ensure_demo_data
    from .routes import router

    # Agent idempotency reuses the legacy ToolInvocation table; ensure it exists
    # even when the app is used without lifespan startup (e.g. TestClient).
    db.init_db()
    ensure_schema()
    if getattr(settings, "STARFIT_SEED_DEMO", True):
        ensure_demo_data()
    app.include_router(router)
    app.include_router(coachapi.router)  # coach-admin React 前端契约层（原始 JSON，无信封）
    app.include_router(portal.router)
    app.add_exception_handler(coachapi._Err, coachapi._err_handler)
