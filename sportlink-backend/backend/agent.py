"""Conversation orchestrator.

Real path: model decides -> returns tool_calls -> backend validates args with
Pydantic -> executes whitelisted Python function -> result appended as a tool
message -> model continues -> final answer.

Fallback path: when Function Calling is unavailable, the same whitelisted
functions are driven by an explicit state machine. Both paths share
build_stage_plan() and tools.execute_tool(), so safety properties are identical.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from . import db
from .config import settings
from .llm import BailianClient, LLMError, TokenStats
from .models import ChatRequest
from .plans import build_stage_plan
from .tools import ToolContext, execute_tool, heuristic_extract, tool_specs

ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})")

SYSTEM_PROMPT = """你是「SoloPilot」的一人公司 AI 员工团队调度员，服务于 6-12 岁儿童上门体育训练业务。
团队包含四位员工，各自有专用工具：
- 接待员工：reception_* （读取/补全客户档案、信息不全时追问）
- 方案员工：plan_* （生成四周一般体育活动方案）
- 商务员工：business_* （查询数据库价目表、生成报价）
- 运营员工：operations_* （查询档期、创建预约、生成跟进草稿）

硬性规则：
1. 只使用白名单里的工具，绝不执行任意代码。工具参数必须是合法 JSON 对象。
2. 只使用家长明确提供的信息；未知字段不要编造，信息不全时先调用 reception_ask_missing_info 追问。
3. 报价金额由后端读取数据库 price_item 并用 Python 计算，你不得自行给出或编造金额。
4. 生成报价单 (business_calculate_quote) 和创建预约 (operations_create_booking) 属于业务承诺，
   必须先调用 shared_request_confirmation 申请令牌，并在用户于下一次请求回传 confirmationId 后，
   把该令牌作为 confirmation_id 传入工具。模型不能自行确认。
5. 创建预约前必须先调用 operations_check_availability 检查时间冲突。
6. 课程方案只做一般体育活动建议，禁止医疗诊断、康复治疗或医学判断。
7. 跟进话术只生成草稿，绝不声称已发送。
8. 回复保持自然、简洁、不骚扰。只输出给家长看的话，不要输出内部 JSON。
"""


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


# ------------------------------------------------------------------ events
def record_event(
    run_id: str,
    step: str,
    name: str,
    status: str,
    duration_ms: int,
    input_obj: Any,
    output_obj: Any,
    log: str,
) -> str:
    event_id = db.new_id("e")
    with db.get_conn() as conn:
        conn.execute(
            'INSERT INTO "AgentAction" '
            '("id","runId","step","name","status","durationMs","inputJson","outputJson","log","createdAt") '
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                run_id,
                step,
                name,
                status,
                duration_ms,
                json.dumps(input_obj, ensure_ascii=False, default=str),
                json.dumps(output_obj, ensure_ascii=False, default=str),
                log,
                db.now_ms(),
            ),
        )
    return event_id


def read_events(run_id: str) -> list[dict[str, Any]]:
    with db.get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM "AgentAction" WHERE "runId" = ? ORDER BY "createdAt", "id"', (run_id,)
        ).fetchall()
    return [
        {
            "id": r["id"],
            "step": r["step"],
            "name": r["name"],
            "status": r["status"],
            "durationMs": r["durationMs"],
            "input": json.loads(r["inputJson"]),
            "output": json.loads(r["outputJson"]),
            "log": r["log"],
            "createdAt": db.ms_to_iso(r["createdAt"]),
        }
        for r in rows
    ]


# ------------------------------------------------------------------ setup
def _resolve(req: ChatRequest) -> tuple[str, str, dict[str, Any]]:
    with db.get_conn() as conn:
        if req.sessionId:
            session = db.get_session(conn, req.sessionId)
            if not session:
                raise ApiError(404, "SESSION_NOT_FOUND", f"会话 {req.sessionId} 不存在")
            lead = conn.execute('SELECT "id" FROM "Lead" WHERE "id" = ?', (session["leadId"],)).fetchone()
            if not lead:
                raise ApiError(404, "LEAD_NOT_FOUND", "会话关联的客户不存在")
            return session["leadId"], session["id"], session["state"]

        lead_id = req.leadId
        if lead_id:
            row = conn.execute('SELECT "id" FROM "Lead" WHERE "id" = ?', (lead_id,)).fetchone()
            if not row:
                raise ApiError(404, "LEAD_NOT_FOUND", f"客户 {lead_id} 不存在")
        else:
            lead_id = db.new_id("l")
            now = db.now_ms()
            conn.execute(
                'INSERT INTO "Lead" '
                '("id","parentName","contact","childAge","goal","location","status","createdAt","updatedAt") '
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    lead_id,
                    req.parentName or "家长（虚构演示）",
                    req.contact or f"demo-{lead_id[:10]}",
                    None,
                    None,
                    None,
                    "new",
                    now,
                    now,
                ),
            )
        session = db.create_session(conn, lead_id)
        return lead_id, session["id"], session["state"]


def _verify_confirmation(req: ChatRequest, session_id: str, state: dict) -> str | None:
    if not req.confirmationId:
        return None
    token = req.confirmationId
    confirmation = state.get("confirmations", {}).get(token)
    if not confirmation:
        raise ApiError(400, "CONFIRMATION_NOT_FOUND", "确认令牌不存在或不属于该会话")
    if confirmation.get("consumed"):
        raise ApiError(409, "CONFIRMATION_ALREADY_USED", "该确认令牌已被使用")
    confirmation["confirmed"] = True
    confirmation["confirmedAt"] = db.now_ms()
    with db.get_conn() as conn:
        db.save_session(conn, session_id, state)
    return token


def _derive_stage(state: dict, lead_id: str, message: str, verified_token: str | None) -> str:
    with db.get_conn() as conn:
        has_plan = conn.execute('SELECT 1 FROM "TrainingPlan" WHERE "leadId" = ? LIMIT 1', (lead_id,)).fetchone() is not None
        has_quote = conn.execute('SELECT 1 FROM "Quote" WHERE "leadId" = ? LIMIT 1', (lead_id,)).fetchone() is not None
        has_booking = conn.execute('SELECT 1 FROM "Booking" WHERE "leadId" = ? LIMIT 1', (lead_id,)).fetchone() is not None

    pending = state.get("pendingConfirmation")
    if verified_token and pending:
        if pending.get("action") == "calculate_quote":
            return "quote_confirm"
        if pending.get("action") == "create_booking":
            return "booking_confirm"
    if pending and not verified_token and ("确认" in message or "同意" in message):
        return "awaiting_confirmation"
    if has_booking:
        return "done"
    if has_quote:
        return "booking_request"
    if re.search(r"\d{1,2}\s*(?:岁|周岁)", message):
        return "info_complete"
    if "档期" in message or "预约" in message:
        return "booking_request"
    return "greet"


def _slot(message: str, session_id: str, state: dict) -> tuple[str, str]:
    found = ISO_RE.findall(message)
    if len(found) >= 2:
        state["proposedSlot"] = {"startAt": found[0], "endAt": found[1]}
    if not state.get("proposedSlot"):
        tz = timezone(timedelta(hours=8))
        base = datetime.now(tz) + timedelta(days=30)
        seed = int(session_id[-6:], 16) % 600
        start = base.replace(hour=15, minute=0, second=0, microsecond=0) + timedelta(minutes=seed)
        state["proposedSlot"] = {
            "startAt": start.isoformat(),
            "endAt": (start + timedelta(hours=1)).isoformat(),
        }
    return state["proposedSlot"]["startAt"], state["proposedSlot"]["endAt"]


def _history(lead_id: str, limit: int = 12) -> list[dict[str, str]]:
    with db.get_conn() as conn:
        rows = conn.execute(
            'SELECT "role","content" FROM "Message" WHERE "leadId" = ? ORDER BY "createdAt" DESC LIMIT ?',
            (lead_id, limit),
        ).fetchall()
    mapping = {"parent": "user", "assistant": "assistant"}
    return [
        {"role": mapping[r["role"]], "content": r["content"]}
        for r in reversed(rows)
        if r["role"] in mapping
    ]


def _system_message(context: dict, verified_token: str | None, llm: BailianClient) -> str:
    extra = [
        f"当前客户 leadId = {context['leadId']}",
        f"当前会话阶段 stage = {context['stage']}",
        f"已抽取字段 = {json.dumps(context.get('extracted', {}), ensure_ascii=False)}",
        f"候选上课时段 = {context.get('proposedStartAt')} ~ {context.get('proposedEndAt')}",
    ]
    if verified_token:
        extra.append(
            f"用户已显式确认令牌 {verified_token}；现在可以调用 business_calculate_quote / "
            "operations_create_booking 并把该值作为 confirmation_id 传入。"
        )
    if context.get("pendingAction"):
        extra.append(f"当前有待确认动作 {context['pendingAction']}，尚未获得用户确认，不要自行执行。")
    extra.append("Function Calling 可用，请通过工具完成任务，不要凭空编造业务数据。")
    return SYSTEM_PROMPT + "\n\n【运行时上下文】\n" + "\n".join(extra)


def _fallback_text(stage: str, results: list[dict[str, Any]]) -> str:
    texts = {
        "greet": "您好，感谢咨询！想先确认一下：孩子几岁、想练什么、什么时间方便上课？",
        "info_complete": "已生成四周课程方案并查询了数据库价目表；正式报价需要您确认后才会生成。",
        "quote_confirm": "报价已按数据库价格生成并存档，需要预约的话请告诉我方便的时间。",
        "booking_request": "档期已查询；创建预约需要您确认后才会执行。",
        "booking_confirm": "已为您创建待确认预约。",
        "awaiting_confirmation": "这一步需要您明确确认，请在请求中回传 confirmationId。",
        "done": "方案和预约都已办妥，还有什么可以帮您？",
    }
    return texts.get(stage, f"已完成本轮处理（{len(results)} 个工具调用）。")


# ------------------------------------------------------------------ main
def run_chat(req: ChatRequest, llm: BailianClient) -> dict[str, Any]:
    started = time.time()
    lead_id, session_id, state = _resolve(req)
    verified_token = _verify_confirmation(req, session_id, state)

    history = _history(lead_id)
    with db.get_conn() as conn:
        db.bump_turn(conn, session_id)
        conn.execute(
            'INSERT INTO "Message" ("id","leadId","role","content","createdAt") VALUES (?,?,?,?,?)',
            (db.new_id("m"), lead_id, "parent", req.message, db.now_ms()),
        )

    stage = _derive_stage(state, lead_id, req.message, verified_token)
    start_at, end_at = _slot(req.message, session_id, state)
    pending = state.get("pendingConfirmation")
    context: dict[str, Any] = {
        "stage": stage,
        "leadId": lead_id,
        "sessionId": session_id,
        "confirmationId": verified_token,
        "pendingAction": pending.get("action") if pending else None,
        "proposedStartAt": start_at,
        "proposedEndAt": end_at,
        "extracted": heuristic_extract(req.message),
    }
    with db.get_conn() as conn:
        db.save_session(conn, session_id, state)

    run_id = db.new_id("r")
    with db.get_conn() as conn:
        conn.execute(
            'INSERT INTO "AgentRun" ("id","leadId","inputMessage","status","summary","durationMs","createdAt") '
            "VALUES (?,?,?,?,?,?,?)",
            (run_id, lead_id, req.message, "running", "", 0, db.now_ms()),
        )

    tool_context = ToolContext(session_id, lead_id, state, verified_token)
    use_fallback = llm.use_state_machine
    record_event(
        run_id,
        "mode",
        "execution_mode",
        "success",
        0,
        {"stage": stage, "useFallback": use_fallback},
        {"mode": "state_machine_fallback" if use_fallback else "function_calling", "probe": llm.probe_result},
        f"执行模式：{'状态机降级（Function Calling 不可用）' if use_fallback else 'Function Calling 工具调用循环'}；{llm.fc_reason}",
    )

    messages: list[dict[str, Any]] = [{"role": "system", "content": _system_message(context, verified_token, llm)}]
    messages.extend(history)
    messages.append({"role": "user", "content": req.message})

    tokens = TokenStats()
    tool_rounds = 0
    final_content: str | None = None
    tool_outcomes: list[dict[str, Any]] = []
    error: ApiError | None = None

    try:
        if use_fallback:
            final_content, tool_rounds, tool_outcomes = _drive_state_machine(
                run_id, llm, context, tool_context, messages, tokens
            )
        else:
            final_content, tool_rounds, tool_outcomes = _drive_function_calling(
                run_id, llm, context, tool_context, messages, tokens
            )
    except LLMError as exc:
        error = ApiError(502, "LLM_ERROR", str(exc))
    except Exception as exc:  # noqa: BLE001 - recorded then surfaced as a clean API error
        error = ApiError(500, "AGENT_RUN_FAILED", f"编排执行失败: {exc}")

    if error:
        final_content = f"处理未完成：{error.message}"
        record_event(run_id, "error", "run_failed", "failed", 0, {}, {"code": error.code}, error.message)

    if not final_content:
        final_content = _fallback_text(stage, tool_outcomes)

    # Token accounting is persisted as an AgentAction event (reuses the existing
    # data model; /agent-runs/{id} aggregates it).
    record_event(
        run_id,
        "usage",
        "token_usage",
        "success",
        0,
        {"mode": llm.mode},
        tokens.as_dict(),
        f"模型调用 {tokens.calls} 次，prompt={tokens.prompt_tokens}, completion={tokens.completion_tokens}, total={tokens.total_tokens}",
    )

    duration_ms = int((time.time() - started) * 1000)
    run_status = "failed" if error else ("needs_input" if stage in ("greet", "awaiting_confirmation") else "completed")
    with db.get_conn() as conn:
        conn.execute(
            'UPDATE "AgentRun" SET "status" = ?, "summary" = ?, "durationMs" = ? WHERE "id" = ?',
            (run_status, final_content[:900], duration_ms, run_id),
        )
        db.save_session(conn, session_id, state)

    if not error:
        with db.get_conn() as conn:
            conn.execute(
                'INSERT INTO "Message" ("id","leadId","role","content","createdAt") VALUES (?,?,?,?,?)',
                (db.new_id("m"), lead_id, "assistant", final_content, db.now_ms()),
            )

    # Stage transition for the next turn.
    executed_names = {o["tool"] for o in tool_outcomes if o.get("ok")}
    if "operations_create_booking" in executed_names:
        state["stage"] = "done"
    elif "business_calculate_quote" in executed_names:
        state["stage"] = "quote_done"
    elif "shared_request_confirmation" in executed_names:
        state["stage"] = "awaiting_user_confirmation"
    elif stage == "greet":
        state["stage"] = "awaiting_info"
    else:
        state["stage"] = stage
    with db.get_conn() as conn:
        db.save_session(conn, session_id, state)
        turn_count = conn.execute('SELECT "turnCount" FROM "ChatSession" WHERE "id" = ?', (session_id,)).fetchone()[0]

    events = read_events(run_id)
    if error:
        raise error

    return {
        "sessionId": session_id,
        "leadId": lead_id,
        "runId": run_id,
        "reply": final_content,
        "sessionState": {
            "stage": state["stage"],
            "turnCount": turn_count,
            "pendingConfirmation": state.get("pendingConfirmation"),
            "proposedSlot": state.get("proposedSlot"),
        },
        "mode": "state_machine_fallback" if use_fallback else "function_calling",
        "llmMode": llm.mode,
        "fcSupported": llm.fc_supported,
        "fcReason": llm.fc_reason,
        "toolRounds": tool_rounds,
        "pendingConfirmation": state.get("pendingConfirmation"),
        "tokenUsage": tokens.as_dict(),
        "durationMs": duration_ms,
        "events": [
            {"step": e["step"], "name": e["name"], "status": e["status"], "durationMs": e["durationMs"], "log": e["log"]}
            for e in events
        ],
    }


# ------------------------------------------------------------------ drivers
def _drive_function_calling(
    run_id: str,
    llm: BailianClient,
    context: dict[str, Any],
    tool_context: ToolContext,
    messages: list[dict[str, Any]],
    tokens: TokenStats,
) -> tuple[str | None, int, list[dict[str, Any]]]:
    specs = tool_specs()
    rounds = 0
    outcomes: list[dict[str, Any]] = []
    final: str | None = None

    for _ in range(settings.MAX_TOOL_ROUNDS):
        response = llm.chat(messages, specs, context)
        tokens.add(response.usage, response.model)

        if not response.tool_calls:
            final = response.content or _fallback_text(context["stage"], outcomes)
            break

        rounds += 1
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": response.content or "",
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]},
                }
                for tc in response.tool_calls
            ],
        }
        messages.append(assistant_message)

        for tc in response.tool_calls:
            name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"]
            record_event(run_id, "tool_call", name, "pending", 0, raw_args, {}, f"模型请求调用工具 {name}")
            outcome = execute_tool(name, raw_args, tool_context)
            outcomes.append(outcome)
            status = "success" if outcome["ok"] else "failed"
            record_event(
                run_id,
                "tool_result",
                name,
                status,
                outcome["durationMs"],
                raw_args,
                outcome,
                f"{name} 执行{('成功' if outcome['ok'] else '失败')}（{outcome['durationMs']}ms，{outcome['code'] or 'ok'}）"
                + (" [幂等命中，未重复创建]" if outcome["deduplicated"] else ""),
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(outcome, ensure_ascii=False, default=str),
                }
            )
    else:
        final = f"已达到工具调用轮次上限（{settings.MAX_TOOL_ROUNDS}），本轮停止以避免无限循环。"
        record_event(run_id, "round_limit", "max_rounds", "failed", 0, {"max": settings.MAX_TOOL_ROUNDS}, {}, final)

    return final, rounds, outcomes


def _drive_state_machine(
    run_id: str,
    llm: BailianClient,
    context: dict[str, Any],
    tool_context: ToolContext,
    messages: list[dict[str, Any]],
    tokens: TokenStats,
) -> tuple[str | None, int, list[dict[str, Any]]]:
    steps = build_stage_plan(context)
    outcomes: list[dict[str, Any]] = []
    for step in steps:
        name, args = step["name"], step["args"]
        record_event(run_id, "tool_call", name, "pending", 0, args, {}, f"[状态机] 调度工具 {name}")
        outcome = execute_tool(name, args, tool_context)
        outcomes.append(outcome)
        record_event(
            run_id,
            "tool_result",
            name,
            "success" if outcome["ok"] else "failed",
            outcome["durationMs"],
            args,
            outcome,
            f"[状态机] {name} 执行{('成功' if outcome['ok'] else '失败')}（{outcome['durationMs']}ms）",
        )

    # A plain (tool-free) model call still produces the parent-facing wording.
    final_context = {**context, "stage": "fallback_final"}
    try:
        response = llm.chat(messages, [], final_context)
        tokens.add(response.usage, response.model)
        final = response.content if response.content and not response.tool_calls else None
    except LLMError:
        final = None
    if not final:
        final = _fallback_text(context["stage"], outcomes)
    return final, (1 if steps else 0), outcomes
