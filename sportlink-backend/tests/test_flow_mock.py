"""Offline (mock Bailian) integration test.

Exercises the complete required business chain and asserts REAL database rows:
客户咨询 -> AI 追问 -> 推荐课程 -> 计算报价 -> 客户确认 -> 查询档期 -> 创建预约

The mock model emits genuine tool_calls; the backend validates args, executes
whitelisted Python functions and appends tool results, i.e. the full Function
Calling loop runs (there is no shortcut around it).
"""
from __future__ import annotations

import json
import os

import pytest

from backend import db
from backend.tools import ToolContext, execute_tool

START = "2027-06-05T15:00:00+08:00"
END = "2027-06-05T16:00:00+08:00"
OVERLAP_START = "2027-06-05T15:30:00+08:00"
OVERLAP_END = "2027-06-05T16:30:00+08:00"

pytestmark = pytest.mark.mock


def chat(client, message: str, **extra):
    response = client.post("/api/v1/ai/chat", json={"message": message, **extra})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True, body
    assert set(body) == {"success", "data", "error", "requestId"}
    assert body["error"] is None
    assert response.headers.get("x-request-id") == body["requestId"]
    return body["data"]


def scalar(raw, sql: str, params: tuple = ()) -> int:
    return int(raw.execute(sql, params).fetchone()[0] or 0)


def test_full_parent_flow_creates_real_db_records(client, raw):
    # ---- 1. 客户咨询 -> AI 追问 ----
    d1 = chat(client, "你好，想咨询儿童上门体育训练", parentName="林女士（虚构）", contact="demo-flow-001")
    session_id, lead_id = d1["sessionId"], d1["leadId"]
    assert d1["mode"] == "function_calling"
    assert d1["fcSupported"] is True
    assert d1["sessionState"]["stage"] == "awaiting_info"
    assert d1["tokenUsage"]["totalTokens"] > 0
    assert d1["toolRounds"] >= 1
    assert any(e["step"] == "tool_call" for e in d1["events"])

    assert scalar(raw, 'SELECT COUNT(*) FROM "Lead"') == 1
    assert scalar(raw, 'SELECT COUNT(*) FROM "Message" WHERE "role" = \'parent\'') == 1
    assert scalar(raw, 'SELECT COUNT(*) FROM "Message" WHERE "role" = \'assistant\'') == 1
    assert scalar(raw, 'SELECT COUNT(*) FROM "TrainingPlan"') == 0
    assert scalar(raw, 'SELECT COUNT(*) FROM "Quote"') == 0

    # ---- 2. 补全信息 -> 推荐课程 -> 请求报价确认 ----
    d2 = chat(
        client,
        "孩子8岁，想提升跳绳和体能，零基础，周末下午可以上课，住在鼓楼区",
        sessionId=session_id,
    )
    assert d2["mode"] == "function_calling"
    quote_pending = d2["pendingConfirmation"]
    assert quote_pending and quote_pending["action"] == "calculate_quote"

    lead = raw.execute('SELECT * FROM "Lead" WHERE "id" = ?', (lead_id,)).fetchone()
    assert lead["childAge"] == 8
    assert "跳绳" in (lead["goal"] or "")
    assert lead["location"] == "鼓楼区"

    assert scalar(raw, 'SELECT COUNT(*) FROM "TrainingPlan" WHERE "leadId" = ?', (lead_id,)) == 1
    plan = raw.execute('SELECT * FROM "TrainingPlan" WHERE "leadId" = ?', (lead_id,)).fetchone()
    weeks = json.loads(plan["weeksJson"])
    assert len(weeks) == 4
    assert all({"theme", "warmup", "mainTraining", "game", "cooldown", "homework"} <= set(w) for w in weeks)
    assert "不构成医疗" in plan["disclaimer"]

    # price list is read from the DB, but NO quote exists before user confirmation
    assert scalar(raw, 'SELECT COUNT(*) FROM "price_item"') == 2
    assert scalar(raw, 'SELECT COUNT(*) FROM "Quote"') == 0
    price_events = [e for e in d2["events"] if e["name"] == "business_get_price_list"]
    assert price_events, "商务员工必须调用价目表工具"

    # ---- 3. 客户确认 -> 计算报价（金额读库 + Python 计算） ----
    d3 = chat(client, "确认报价", sessionId=session_id, confirmationId=quote_pending["token"])
    assert d3["mode"] == "function_calling"

    assert scalar(raw, 'SELECT COUNT(*) FROM "Quote" WHERE "leadId" = ?', (lead_id,)) == 1
    quote = raw.execute('SELECT * FROM "Quote" WHERE "leadId" = ?', (lead_id,)).fetchone()
    unit = scalar(raw, 'SELECT "unitPriceCents" FROM "price_item" WHERE "packageType" = \'package4\'')
    assert quote["totalCents"] == unit == 49900
    assert quote["currency"] == "CNY"
    items = raw.execute('SELECT * FROM "QuoteItem" WHERE "quoteId" = ?', (quote["id"],)).fetchall()
    assert len(items) == 1
    assert items[0]["quantity"] == 1
    assert items[0]["unitPriceCents"] == unit
    assert items[0]["amountCents"] == unit * 1 == quote["totalCents"]

    # ---- 4. 查询档期 -> 请求预约确认 ----
    d4 = chat(client, f"帮我查一下 {START} 到 {END} 的档期并预约", sessionId=session_id)
    booking_pending = d4["pendingConfirmation"]
    assert booking_pending and booking_pending["action"] == "create_booking"
    assert scalar(raw, 'SELECT COUNT(*) FROM "Booking"') == 0
    assert any(e["name"] == "operations_check_availability" for e in d4["events"])

    # ---- 5. 客户确认 -> 创建预约 ----
    d5 = chat(client, "确认预约", sessionId=session_id, confirmationId=booking_pending["token"])
    assert d5["sessionState"]["stage"] == "done"

    assert scalar(raw, 'SELECT COUNT(*) FROM "Booking" WHERE "leadId" = ?', (lead_id,)) == 1
    booking = raw.execute('SELECT * FROM "Booking" WHERE "leadId" = ?', (lead_id,)).fetchone()
    assert booking["status"] == "pending"
    assert booking["startAt"] == db.iso_to_ms(START)
    assert booking["endAt"] == db.iso_to_ms(END)

    # ---- 6. 编排与统计接口 ----
    run_id = d5["runId"]
    run_res = client.get(f"/api/v1/agent-runs/{run_id}")
    assert run_res.status_code == 200
    run_data = run_res.json()["data"]
    assert run_data["status"] == "completed"
    assert run_data["toolCallCount"] >= 1
    assert run_data["tokenUsage"]["totalTokens"] > 0

    events_res = client.get(f"/api/v1/agent-runs/{run_id}/events")
    assert events_res.status_code == 200
    events = events_res.json()["data"]["events"]
    steps = {e["step"] for e in events}
    assert {"mode", "tool_call", "tool_result", "usage"} <= steps
    tool_results = [json.loads(raw.execute('SELECT "outputJson" FROM "AgentAction" WHERE "id" = ?', (e["id"],)).fetchone()[0]) for e in events if e["step"] == "tool_result"]
    assert any(r.get("ok") for r in tool_results)

    summary = client.get("/api/v1/dashboard/summary").json()["data"]
    assert summary["leads"]["total"] == 1
    assert summary["quotes"]["total"] == 1
    assert summary["quotes"]["totalCents"] == 49900
    assert summary["bookings"]["total"] == 1
    assert summary["trainingPlans"] == 1
    assert summary["agentRuns"] == 5

    # Session / run / idempotency records all persisted.
    assert scalar(raw, 'SELECT COUNT(*) FROM "ChatSession"') == 1
    assert scalar(raw, 'SELECT "turnCount" FROM "ChatSession" WHERE "id" = ?', (session_id,)) == 5
    assert scalar(raw, 'SELECT COUNT(*) FROM "AgentRun"') == 5
    assert scalar(raw, 'SELECT COUNT(*) FROM "ToolInvocation"') > 0


def test_tool_whitelist_and_pydantic_validation(raw):
    ctx = ToolContext("s_test", "l_test", {"confirmations": {}}, None)

    blocked = execute_tool("os_system", {"cmd": "rm -rf /"}, ctx)
    assert blocked["ok"] is False
    assert blocked["code"] == "TOOL_NOT_WHITELISTED"
    assert "reception_get_lead" in blocked["error"]["allowed"]

    bad = execute_tool("plan_create_training_plan", {"lead_id": "x", "age": 99, "goal": "跳绳", "experience": "零基础"}, ctx)
    assert bad["ok"] is False
    assert bad["code"] == "INVALID_TOOL_ARGS"

    extra = execute_tool("business_get_price_list", {"unexpected": 1}, ctx)
    assert extra["ok"] is False
    assert extra["code"] == "INVALID_TOOL_ARGS"


def test_confirmation_gate_cannot_be_bypassed_by_model(raw):
    state = {"confirmations": {}}
    ctx = ToolContext("s_conf", "l_conf", state, None)
    args = {"lead_id": "l_conf", "package_type": "package4", "quantity": 1, "confirmation_id": "forged"}

    without_token = execute_tool("business_calculate_quote", args, ctx)
    assert without_token["ok"] is False
    assert without_token["code"] == "CONFIRMATION_REQUIRED"

    # A token that exists but was never confirmed by the HTTP client is useless.
    state["confirmations"]["real_token"] = {
        "action": "calculate_quote", "confirmed": False, "consumed": False,
    }
    unconfirmed = execute_tool("business_calculate_quote", {**args, "confirmation_id": "real_token"}, ctx)
    assert unconfirmed["ok"] is False
    assert unconfirmed["code"] == "CONFIRMATION_NOT_GRANTED"
    assert scalar(raw, 'SELECT COUNT(*) FROM "Quote"') == 0


def test_booking_conflict_and_idempotency(raw):
    with db.get_conn() as conn:
        conn.execute(
            'INSERT INTO "Lead" ("id","parentName","contact","status","createdAt","updatedAt") VALUES (?,?,?,?,?,?)',
            ("l_conf2", "测试家长（虚构）", "demo-conflict", "new", db.now_ms(), db.now_ms()),
        )
        session_id = db.create_session(conn, "l_conf2")["id"]

    state = {"confirmations": {}}
    ctx = ToolContext(session_id, "l_conf2", state, None)
    base = {"lead_id": "l_conf2", "start_at": START, "end_at": END}

    state["confirmations"]["tok_a"] = {"action": "create_booking", "confirmed": True, "consumed": False}
    first = execute_tool("operations_create_booking", {**base, "confirmation_id": "tok_a", "note": "第一次"}, ctx)
    assert first["ok"] is True, first
    assert scalar(raw, 'SELECT COUNT(*) FROM "Booking"') == 1

    # Same call again -> deduplicated, no second record.
    repeat = execute_tool("operations_create_booking", {**base, "confirmation_id": "tok_a", "note": "第一次"}, ctx)
    assert repeat["ok"] is True
    assert repeat["deduplicated"] is True
    assert scalar(raw, 'SELECT COUNT(*) FROM "Booking"') == 1

    # Overlapping slot with a fresh confirmed token -> conflict, still one record.
    state["confirmations"]["tok_b"] = {"action": "create_booking", "confirmed": True, "consumed": False}
    overlap = execute_tool(
        "operations_create_booking",
        {
            "lead_id": "l_conf2",
            "start_at": OVERLAP_START,
            "end_at": OVERLAP_END,
            "confirmation_id": "tok_b",
        },
        ctx,
    )
    assert overlap["ok"] is False
    assert overlap["code"] == "BOOKING_CONFLICT"
    assert scalar(raw, 'SELECT COUNT(*) FROM "Booking"') == 1

    # Non-overlapping adjacent slot is allowed.
    state["confirmations"]["tok_c"] = {"action": "create_booking", "confirmed": True, "consumed": False}
    adjacent = execute_tool(
        "operations_create_booking",
        {
            "lead_id": "l_conf2",
            "start_at": "2027-06-05T16:00:00+08:00",
            "end_at": "2027-06-05T17:00:00+08:00",
            "confirmation_id": "tok_c",
        },
        ctx,
    )
    assert adjacent["ok"] is True, adjacent
    assert scalar(raw, 'SELECT COUNT(*) FROM "Booking"') == 2


def test_state_machine_fallback_still_creates_records(make_app, raw):
    """FORCE_STATE_MACHINE=true simulates a region/model without Function Calling."""
    fallback_client, llm = make_app(force_state_machine=True)
    with fallback_client as c:
        assert llm.fc_supported is False
        assert "状态机" in llm.fc_reason

        d1 = chat(c, "你好，想咨询儿童上门体育训练", parentName="王女士（虚构）", contact="demo-fallback")
        sid = d1["sessionId"]
        assert d1["mode"] == "state_machine_fallback"
        assert d1["fcSupported"] is False
        assert d1["sessionState"]["stage"] == "awaiting_info"

        d2 = chat(c, "孩子8岁，想练跳绳，零基础，周末下午有空", sessionId=sid)
        pending = d2["pendingConfirmation"]
        assert d2["mode"] == "state_machine_fallback"
        assert scalar(raw, 'SELECT COUNT(*) FROM "TrainingPlan"') == 1

        d3 = chat(c, "确认报价", sessionId=sid, confirmationId=pending["token"])
        assert d3["mode"] == "state_machine_fallback"
        assert scalar(raw, 'SELECT COUNT(*) FROM "Quote"') == 1

        d4 = chat(c, f"帮我查一下 {START} 到 {END} 的档期并预约", sessionId=sid)
        pending2 = d4["pendingConfirmation"]
        d5 = chat(c, "确认预约", sessionId=sid, confirmationId=pending2["token"])

        assert d5["sessionState"]["stage"] == "done"
        assert scalar(raw, 'SELECT COUNT(*) FROM "Booking"') == 1
        assert scalar(raw, 'SELECT COUNT(*) FROM "AgentAction" WHERE "log" LIKE \'%[状态机]%\'') > 0


def test_health_reports_connectivity_probe(client):
    body = client.get("/api/v1/health").json()
    assert body["success"] is True
    data = body["data"]
    assert data["mode"] == "mock"
    assert data["model"] == "qwen3.7-plus"
    assert data["fallbackModel"] == "qwen3.8-max"
    assert data["probe"]["checked"] is True
    assert data["probe"]["fcSupported"] is True
    assert data["useStateMachine"] is False


def test_missing_run_and_bad_request_return_envelope(client):
    missing = client.get("/api/v1/agent-runs/nope")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "AGENT_RUN_NOT_FOUND"

    bad = client.post("/api/v1/ai/chat", json={"message": ""})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"


def test_real_mode_without_key_fails_fast():
    from backend.config import Settings
    from backend.llm import BailianClient, LLMError

    cfg = Settings(LLM_MODE="real", DASHSCOPE_API_KEY="", DATABASE_PATH=os.environ["SOLOPILOT_DATABASE_PATH"])
    with pytest.raises(LLMError, match="未配置 DASHSCOPE_API_KEY"):
        BailianClient(cfg)
