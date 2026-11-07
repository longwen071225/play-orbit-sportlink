"""SoloPilot FastAPI service.

Only four new /api/v1/* business endpoints are added. The legacy
Node/Fastify service keeps its own routes untouched; both share the same
SQLite business tables, and the Python service is the single writer (see
README_SoloPilot.md).
"""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from typing import Any

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .agent import ApiError, read_events, run_chat
from .config import settings
from .llm import BailianClient
from .models import ChatRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # Startup connectivity + Function Calling capability test.
    app.state.probe = app.state.llm.probe()
    yield


def create_app(llm: BailianClient | None = None) -> FastAPI:
    app = FastAPI(
        title="SoloPilot AI Backend",
        version="1.0.0",
        description="阿里云百炼 Function Calling 驱动的独立体育教练 AI 员工系统（仅后端）",
        docs_url=None,  # /docs is self-hosted below: Swagger assets ship with the repo (offline demo safe).
        lifespan=lifespan,
    )
    app.state.llm = llm or BailianClient()
    app.state.probe = {}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    swagger_dir = Path(__file__).resolve().parent / "static" / "swagger-ui"
    if swagger_dir.is_dir():
        app.mount("/static/swagger-ui", StaticFiles(directory=swagger_dir), name="swagger-ui-static")

    # Whole static root (pose assets, Motion Coach training page, ...).
    static_root = Path(__file__).resolve().parent / "static"
    if static_root.is_dir():
        app.mount("/static", StaticFiles(directory=static_root), name="starfit-static")

    @app.get("/docs", include_in_schema=False)
    async def custom_docs() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
            swagger_css_url="/static/swagger-ui/swagger-ui.css",
        )

    def custom_openapi() -> dict[str, Any]:
        # StarFit routes read the Authorization header manually, so FastAPI cannot
        # infer security. Declare it here so Swagger UI shows Authorize + lock icons
        # and frontend consumers see which endpoints need a Bearer token.
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "HMAC",
                "description": "先调用 POST /api/auth/login 获取 token，再粘贴到此处。",
            }
        }
        public_paths = {"/api/auth/login", "/api/starfit/health"}
        for path, item in schema["paths"].items():
            if path.startswith("/api/v1/") or path in public_paths:
                continue
            for op in item.values():
                if isinstance(op, dict) and "responses" in op:
                    op["security"] = [{"BearerAuth": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    def envelope(request: Request, data: Any, status_code: int = 200) -> JSONResponse:
        response = JSONResponse(
            status_code=status_code,
            content={"success": True, "data": data, "error": None, "requestId": request.state.request_id},
        )
        response.headers["x-request-id"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "error": {"code": exc.code, "message": exc.message, "details": exc.details},
                "requestId": getattr(request.state, "request_id", str(uuid.uuid4())),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "请求参数校验失败",
                    "details": json.loads(json.dumps(exc.errors(), default=str)),
                },
                "requestId": getattr(request.state, "request_id", str(uuid.uuid4())),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": None,
                "error": {"code": "INTERNAL_ERROR", "message": str(exc), "details": None},
                "requestId": getattr(request.state, "request_id", str(uuid.uuid4())),
            },
        )

    # ------------------------------------------------------------ health
    @app.get("/api/v1/health", tags=["system"], summary="健康检查：百炼连通性与 Function Calling 能力")
    def health(request: Request, recheck: bool = False):
        llm: BailianClient = request.app.state.llm
        if recheck or not request.app.state.probe:
            request.app.state.probe = llm.probe()
        return envelope(
            request,
            {
                "status": "ok",
                "mode": llm.mode,
                "model": llm.primary_model,
                "fallbackModel": llm.fallback_model,
                "apiKeyConfigured": settings.api_key_present,
                "probe": request.app.state.probe,
                "useStateMachine": llm.use_state_machine,
                "database": settings.DATABASE_PATH,
            },
        )

    # ------------------------------------------------------------ chat
    @app.post("/api/v1/ai/chat", tags=["AI"], summary="发送客户消息，返回 AI 回复和会话状态")
    def chat(req: ChatRequest, request: Request):
        return envelope(request, run_chat(req, request.app.state.llm))

    # ------------------------------------------------------------ runs
    @app.get("/api/v1/agent-runs/{run_id}", tags=["Agent"], summary="查看 Agent 执行情况")
    def get_run(run_id: str, request: Request):
        with db.get_conn() as conn:
            row = conn.execute('SELECT * FROM "AgentRun" WHERE "id" = ?', (run_id,)).fetchone()
        if not row:
            raise ApiError(404, "AGENT_RUN_NOT_FOUND", f"AgentRun {run_id} 不存在")
        events = read_events(run_id)
        usage_events = [e["output"] for e in events if e["step"] == "usage"]
        token_usage: dict[str, Any] = {
            "promptTokens": sum(u.get("promptTokens", 0) for u in usage_events),
            "completionTokens": sum(u.get("completionTokens", 0) for u in usage_events),
            "totalTokens": sum(u.get("totalTokens", 0) for u in usage_events),
            "calls": sum(u.get("calls", 0) for u in usage_events),
        }
        tool_calls = [e for e in events if e["step"] == "tool_call"]
        modes = [e["output"].get("mode") for e in events if e["step"] == "mode"]
        return envelope(
            request,
            {
                "id": row["id"],
                "leadId": row["leadId"],
                "inputMessage": row["inputMessage"],
                "status": row["status"],
                "summary": row["summary"],
                "durationMs": row["durationMs"],
                "createdAt": db.ms_to_iso(row["createdAt"]),
                "mode": modes[0] if modes else None,
                "toolCallCount": len(tool_calls),
                "tools": [e["name"] for e in tool_calls],
                "tokenUsage": token_usage,
                "eventCount": len(events),
                "failedEvents": [e["name"] for e in events if e["status"] == "failed"],
            },
        )

    @app.get("/api/v1/agent-runs/{run_id}/events", tags=["Agent"], summary="查看工具调用轨迹")
    def get_events(run_id: str, request: Request):
        with db.get_conn() as conn:
            exists = conn.execute('SELECT 1 FROM "AgentRun" WHERE "id" = ?', (run_id,)).fetchone()
        if not exists:
            raise ApiError(404, "AGENT_RUN_NOT_FOUND", f"AgentRun {run_id} 不存在")
        events = read_events(run_id)
        return envelope(request, {"runId": run_id, "count": len(events), "events": events})

    # ------------------------------------------------------------ dashboard
    @app.get("/api/v1/dashboard/summary", tags=["Dashboard"], summary="客户、报价及预约统计")
    def dashboard(request: Request):
        with db.get_conn() as conn:
            def scalar(sql: str, params: tuple = ()) -> int:
                value = conn.execute(sql, params).fetchone()[0]
                return int(value or 0)

            leads_total = scalar('SELECT COUNT(*) FROM "Lead"')
            lead_status: dict[str, int] = {
                r["status"]: r["n"]
                for r in conn.execute('SELECT "status", COUNT(*) AS n FROM "Lead" GROUP BY "status"')
            }
            quotes_total = scalar('SELECT COUNT(*) FROM "Quote"')
            quote_sum = scalar('SELECT COALESCE(SUM("totalCents"),0) FROM "Quote"')
            quote_items = scalar('SELECT COUNT(*) FROM "QuoteItem"')
            bookings_total = scalar('SELECT COUNT(*) FROM "Booking"')
            booking_status: dict[str, int] = {
                r["status"]: r["n"]
                for r in conn.execute('SELECT "status", COUNT(*) AS n FROM "Booking" GROUP BY "status"')
            }
            plans = scalar('SELECT COUNT(*) FROM "TrainingPlan"')
            messages = scalar('SELECT COUNT(*) FROM "Message"')
            runs = scalar('SELECT COUNT(*) FROM "AgentRun"')
            actions = scalar('SELECT COUNT(*) FROM "AgentAction"')
            tool_invocations = scalar('SELECT COUNT(*) FROM "ToolInvocation"')
            prices = db.list_prices(conn)

        llm: BailianClient = request.app.state.llm
        return envelope(
            request,
            {
                "leads": {"total": leads_total, "byStatus": lead_status},
                "quotes": {
                    "total": quotes_total,
                    "items": quote_items,
                    "totalCents": quote_sum,
                    "totalYuan": f"{quote_sum / 100:.2f}",
                },
                "bookings": {"total": bookings_total, "byStatus": booking_status},
                "trainingPlans": plans,
                "messages": messages,
                "agentRuns": runs,
                "agentActions": actions,
                "toolInvocations": tool_invocations,
                "priceList": prices,
                "model": {
                    "mode": llm.mode,
                    "primary": llm.primary_model,
                    "fallback": llm.fallback_model,
                    "fcSupported": llm.fc_supported,
                    "fcReason": llm.fc_reason,
                    "useStateMachine": llm.use_state_machine,
                },
            },
        )

    # StarFit (星动到家) additive module: does not alter any legacy route.
    from .starfit import register_starfit

    register_starfit(app)
    return app


app = create_app()
