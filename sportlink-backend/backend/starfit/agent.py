"""StarFit AI Agent: real Function Calling against Alibaba Bailian.

Reuses backend.llm.BailianClient (probe / retries / fallback model / token
accounting) and backend.db / backend.models. The offline driver emits genuine
tool_calls structures so the whole whitelist -> Pydantic -> DB -> confirmation
loop runs without an API key. Nothing here is a second server: one FastAPI app,
one SQLite file, one LLM client.

Safety invariants:
  * Whitelist: names outside TOOL_REGISTRY are never executed.
  * Pydantic extra="forbid": the model cannot smuggle unexpected arguments.
  * Confirmation gate: create_booking needs a user-supplied confirmation token
    that exists in the session state; the model cannot mint it.
  * Idempotency: (session, tool, args) is cached in the existing ToolInvocation table.
  * No fabricated data: profiles, history, exercises, slots and stars are read
    from real rows. The AI never creates training records or growth stars.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import ValidationError

from .. import db
from ..agent import ApiError
from ..config import settings
from ..llm import BailianClient, LLMResponse, TokenStats
from ..models import StrictModel
from . import services
from .auth import assert_child_access

SAFETY_NOTE = (
    "本平台仅提供一般儿童体育活动建议，不构成医疗诊断、康复或任何医学判断；"
    "如孩子有伤病、明显疼痛或健康风险，请停止训练并咨询专业医生。"
)

SYSTEM_PROMPT = f"""你是「星动到家 StarFit」的儿童上门体育服务 AI 助手，服务 5-12 岁儿童及其家长。

硬性规则：
1. 只使用白名单工具，参数必须是合法 JSON 对象；绝不执行任意代码。
2. 儿童档案、训练历史、动作知识库、教练档期、成长星图都必须通过工具读取真实数据，
   不得编造儿童信息、训练记录、可预约时间或成长奖励。
3. 涉及写入的操作（创建预约订单）必须先调用 request_confirmation 申请确认令牌。
   当用户表达预约意图且信息齐全时，立即调用 request_confirmation（不要只用文字询问），
   把返回的 confirmationId 交给前端展示确认按钮；用户下一次请求回传该令牌后，
   再把它作为 confirmation_id 传入 create_booking。
   模型不能自行确认，也不能自行编造令牌。
4. 金额由后端按课程价目表确定，模型不得给出或编造价格。
5. 训练计划仅为一般体育活动建议；遇伤病、疼痛或健康风险不做医学诊断，提示寻求专业帮助：{SAFETY_NOTE}
6. 课后反馈只能基于教练已提交的真实训练记录生成，不得补写不存在的表现数据。
7. 回复自然简洁，只输出给家长/教练看的话，不要输出内部 JSON。
"""


# ------------------------------------------------------------------ tool args
class GetChildProfileArgs(StrictModel):
    child_id: str = ""


class GetTrainingHistoryArgs(StrictModel):
    child_id: str = ""
    limit: int = 5


class SearchExercisesArgs(StrictModel):
    category: str | None = None
    keyword: str | None = None
    age: int | None = None
    limit: int = 5


class GenerateTrainingPlanArgs(StrictModel):
    child_id: str = ""
    goal: str = "综合运动基础"
    weeks: int = 4


class SearchCoachesArgs(StrictModel):
    sport_type: str | None = None
    area: str | None = None
    available_on: str | None = None


class GetAvailableSlotsArgs(StrictModel):
    coach_id: str
    from_date: str | None = None
    to_date: str | None = None


class GetGrowthProgressArgs(StrictModel):
    child_id: str = ""


class GenerateCourseReportArgs(StrictModel):
    booking_id: str
    confirmation_id: str | None = None


class CreateBookingArgs(StrictModel):
    child_id: str = ""
    service_id: str
    start_at: str
    end_at: str
    confirmation_id: str
    note: str | None = None


class RequestConfirmationArgs(StrictModel):
    action: str
    summary: str
    payload: dict[str, Any] | None = None


class GetMotionSessionArgs(StrictModel):
    session_id: str
    limit: int = 10


# ------------------------------------------------------------------ plumbing
class ToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ToolContext:
    conn: Any
    user: dict[str, Any]
    session_id: str
    state: dict[str, Any]
    confirmation_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolDef:
    name: str
    description: str
    args_model: type[StrictModel]
    func: Callable[[dict[str, Any], ToolContext], dict[str, Any]]
    high_risk: bool = False


def _resolve_child_id(conn: Any, user: dict[str, Any], child_id: str) -> str:
    if child_id:
        assert_child_access(conn, user, child_id)
        return child_id
    row = conn.execute(
        'SELECT "id" FROM "sf_child" WHERE "guardianId"=? ORDER BY "createdAt" LIMIT 1',
        (user["id"],),
    ).fetchone()
    if not row:
        raise ToolError("CHILD_NOT_FOUND", "尚未创建儿童档案，请先调用 /api/children 创建")
    assert_child_access(conn, user, row["id"])
    return row["id"]


def _check_confirmation(ctx: ToolContext, action: str) -> None:
    token = ctx.confirmation_id
    if not token:
        raise ToolError("CONFIRMATION_REQUIRED", f"{action} 需要用户明确确认，请先调用 request_confirmation 并回传 confirmationId")
    pendings = ctx.state.setdefault("pendingConfirmations", [])
    match = next(
        (p for p in pendings if p.get("id") == token and p.get("action") == action and not p.get("used")),
        None,
    )
    if not match:
        raise ToolError("INVALID_CONFIRMATION", "确认令牌无效、动作不匹配或已使用")
    match["used"] = True


# ------------------------------------------------------------------ tool implementations
def _get_child_profile(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    cid = _resolve_child_id(ctx.conn, ctx.user, args["child_id"])
    return {"child": services.get_child(ctx.conn, ctx.user, cid)}


def _get_training_history(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    cid = _resolve_child_id(ctx.conn, ctx.user, args["child_id"])
    rows = ctx.conn.execute(
        'SELECT * FROM "sf_training_record" WHERE "childId"=? ORDER BY "createdAt" DESC LIMIT ?',
        (cid, max(1, min(20, args["limit"]))),
    ).fetchall()
    records = [services.training_record_out(r) for r in rows]
    return {"childId": cid, "total": len(records), "records": records, "note": "仅返回教练已提交的真实训练记录"}


def _search_exercises(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    result = services.list_exercises(
        ctx.conn, args.get("category"), args.get("keyword"), args.get("age"), 1,
        max(1, min(20, args["limit"])),
    )
    return {"total": result["total"], "exercises": result["items"], "note": "动作来自平台知识库，媒体链接为空表示暂无资源"}


def _generate_training_plan(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    cid = _resolve_child_id(ctx.conn, ctx.user, args["child_id"])
    child = services.get_child(ctx.conn, ctx.user, cid)
    history = ctx.conn.execute(
        'SELECT "content" FROM "sf_training_record" WHERE "childId"=? ORDER BY "createdAt" DESC LIMIT 5',
        (cid,),
    ).fetchall()
    exercises = services.list_exercises(ctx.conn, None, args.get("goal"), child["age"], 1, 12)
    picked = exercises["items"][:6] or services.list_exercises(ctx.conn, None, None, child["age"], 1, 6)["items"]
    weeks = max(1, min(8, args["weeks"]))
    plan = {
        "title": f"{child['nickname']} 的 {weeks} 周运动建议",
        "childId": cid,
        "age": child["age"],
        "goal": args["goal"],
        "trainingGoals": child["trainingGoals"],
        "basedOn": {
            "priorTrainingRecords": len(history),
            "exerciseKnowledgeBase": len(picked),
        },
        "weeks": [
            {
                "week": i + 1,
                "focus": ["基础动作熟悉", "协调与平衡", "节奏与耐力", "综合游戏"][i % 4],
                "exercises": [
                    {"exerciseId": e["exerciseId"], "name": e["name"], "category": e["category"]}
                    for e in picked[:3]
                ],
            }
            for i in range(weeks)
        ],
        "exerciseDetails": picked,
        "disclaimer": SAFETY_NOTE,
        "saved": False,
        "note": "这是基于真实档案/记录/知识库生成的结构化建议，未写入训练计划表，不构成体能评估",
    }
    return plan


def _search_coaches(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    result = services.list_coaches(
        ctx.conn, args.get("sport_type"), args.get("area"), args.get("available_on"), 1, 20
    )
    for coach in result["items"]:
        slots = services.get_coach_slots(ctx.conn, coach["id"], args.get("available_on"), args.get("available_on"))
        coach["openSlots"] = [s for s in slots["slots"] if s["status"] == "OPEN"]
    return {"total": result["total"], "coaches": result["items"]}


def _get_available_slots(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return services.get_coach_slots(ctx.conn, args["coach_id"], args.get("from_date"), args.get("to_date"))


def _get_growth_progress(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    cid = _resolve_child_id(ctx.conn, ctx.user, args["child_id"])
    star_map = services.get_stars(ctx.conn, ctx.user, cid)
    count = ctx.conn.execute(
        'SELECT COUNT(*) FROM "sf_training_record" WHERE "childId"=?', (cid,)
    ).fetchone()[0]
    return {
        "childId": cid,
        "starTotal": star_map["total"],
        "stars": star_map["stars"],
        "constellations": star_map["constellations"],
        "completedTrainingRecords": int(count),
        "disclaimer": star_map["disclaimer"],
    }


def _generate_course_report(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    booking = ctx.conn.execute('SELECT * FROM "sf_booking" WHERE "id"=?', (args["booking_id"],)).fetchone()
    if not booking:
        raise ToolError("BOOKING_NOT_FOUND", f"订单 {args['booking_id']} 不存在")
    record = ctx.conn.execute(
        'SELECT * FROM "sf_training_record" WHERE "bookingId"=? ORDER BY "createdAt" DESC LIMIT 1',
        (args["booking_id"],),
    ).fetchone()
    if not record:
        raise ToolError("TRAINING_RECORD_REQUIRED", "本次课程尚无教练提交的真实训练记录，无法生成课后反馈")
    assert_child_access(ctx.conn, ctx.user, booking["childId"])
    service = ctx.conn.execute('SELECT * FROM "sf_service" WHERE "id"=?', (booking["serviceId"],)).fetchone()
    history = ctx.conn.execute(
        'SELECT "content","createdAt" FROM "sf_training_record" WHERE "childId"=? AND "id"<>? ORDER BY "createdAt" DESC LIMIT 3',
        (booking["childId"], record["id"]),
    ).fetchall()
    report = {
        "bookingId": booking["id"],
        "childId": booking["childId"],
        "course": service["title"] if service else "课程",
        "durationMinutes": record["durationMinutes"],
        "coachObservation": record["content"],
        "coachPerformance": services._loads(record["performance"], {}),
        "priorSessionCount": len(history),
        "priorObservations": [h["content"] for h in history],
        "summary": f"本次课程时长 {record['durationMinutes']} 分钟。教练记录：{record['content']}",
        "homePracticeSuggestion": "可复习本次已掌握的动作，具体家庭任务由教练布置后确认。",
        "disclaimer": SAFETY_NOTE,
        "source": "仅基于教练提交的真实训练记录与历史记录，未补写任何不存在的表现数据",
        "saved": False,
    }
    if args.get("confirmation_id"):
        _check_confirmation(ctx, "save_course_report")
        now = db.now_ms()
        ctx.conn.execute(
            'INSERT INTO "sf_training_plan" '
            '("id","childId","coachId","agentSessionId","title","planJson","disclaimer","status","createdAt") '
            "VALUES (?,?,?,?,?,?,?,'CONFIRMED',?)",
            (db.new_id("tp"), booking["childId"], booking["coachId"], ctx.session_id,
             f"课后反馈 - {service['title'] if service else '课程'}",
             json.dumps(report, ensure_ascii=False), SAFETY_NOTE, now),
        )
        report["saved"] = True
    else:
        report["requiresConfirmation"] = True
        report["note"] = "报告为草稿；需调用 request_confirmation(action='save_course_report') 并回传令牌后才保存"
    return report


def _create_booking(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    _check_confirmation(ctx, "create_booking")
    cid = _resolve_child_id(ctx.conn, ctx.user, args["child_id"])
    payload = {
        "childId": cid,
        "serviceId": args["service_id"],
        "startAt": args["start_at"],
        "endAt": args["end_at"],
        "note": args.get("note") or "由 AI Agent 在家长确认后创建",
    }
    return {"booking": services.create_booking(ctx.conn, ctx.user, payload)}


def _request_confirmation(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    token = "cf_" + db.new_id("")
    pendings = ctx.state.setdefault("pendingConfirmations", [])
    pendings.append(
        {
            "id": token,
            "action": args["action"],
            "summary": args["summary"],
            "payload": args.get("payload") or {},
            "used": False,
            "createdAt": db.now_ms(),
        }
    )
    return {
        "confirmationId": token,
        "action": args["action"],
        "summary": args["summary"],
        "message": "该操作需要用户明确确认，请在下一次请求中回传 confirmationId",
        "expiresInSeconds": 3600,
    }


def _get_motion_session(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    from . import pose as pose_engine

    row = ctx.conn.execute(
        'SELECT * FROM "sf_training_session" WHERE "id"=?', (args["session_id"],)
    ).fetchone()
    if not row:
        raise ToolError("SESSION_NOT_FOUND", f"训练会话 {args['session_id']} 不存在")
    assert_child_access(ctx.conn, ctx.user, row["childId"])
    config = pose_engine.MOTION_CONFIGS.get(row["exerciseId"]) or {}
    events = ctx.conn.execute(
        'SELECT "type","code","confidence","metricsJson","createdAt" FROM "sf_pose_feedback_event" '
        'WHERE "sessionId"=? ORDER BY "createdAt" DESC LIMIT ?',
        (row["id"], max(1, min(50, int(args["limit"])))),
    ).fetchall()
    result = ctx.conn.execute(
        'SELECT * FROM "sf_training_result" WHERE "sessionId"=?', (row["id"],)
    ).fetchone()
    counters = {
        "repCount": row["repCount"], "validRepCount": row["validRepCount"], "holdMs": row["holdMs"],
        "errorCounts": services._loads(row["errorCountsJson"], {}), "avgConfidence": row["avgConfidence"],
        "poseLostCount": row["poseLostCount"],
    }
    return {
        "session": {
            "id": row["id"], "childId": row["childId"], "exerciseId": row["exerciseId"],
            "mode": row["mode"], "status": row["status"], "taskId": row["taskId"],
            "startedAt": db.ms_to_iso(row["startedAt"]) if row["startedAt"] else None,
            "endedAt": db.ms_to_iso(row["endedAt"]) if row["endedAt"] else None,
        },
        "counters": pose_engine.counters_out(counters, config),
        "completionCheck": pose_engine.evaluate_completion(config, counters),
        "recentEvents": [
            {"type": e["type"], "code": e["code"], "confidence": e["confidence"],
             "at": db.ms_to_iso(e["createdAt"])}
            for e in reversed(events)
        ],
        "result": services.training_result_out(result) if result else None,
    }


TOOL_REGISTRY: dict[str, ToolDef] = {
    "get_child_profile": ToolDef("get_child_profile", "读取当前用户有权访问的儿童档案", GetChildProfileArgs, _get_child_profile),
    "get_training_history": ToolDef("get_training_history", "查询儿童真实历史训练记录", GetTrainingHistoryArgs, _get_training_history),
    "search_exercises": ToolDef("search_exercises", "按类别/关键词/年龄检索运动动作知识库", SearchExercisesArgs, _search_exercises),
    "generate_training_plan": ToolDef("generate_training_plan", "根据年龄、目标与真实记录生成结构化运动建议（只读，不落库）", GenerateTrainingPlanArgs, _generate_training_plan),
    "search_coaches": ToolDef("search_coaches", "按运动类型/服务地区/日期筛选已审核教练", SearchCoachesArgs, _search_coaches),
    "get_available_slots": ToolDef("get_available_slots", "查询教练真实可预约档期", GetAvailableSlotsArgs, _get_available_slots),
    "get_growth_progress": ToolDef("get_growth_progress", "查询儿童成长星图与训练进度", GetGrowthProgressArgs, _get_growth_progress),
    "get_motion_session": ToolDef("get_motion_session", "读取一次 AI 陪练训练会话的真实计数与规则引擎判定结果", GetMotionSessionArgs, _get_motion_session),
    "generate_course_report": ToolDef("generate_course_report", "基于真实训练记录生成课后反馈草稿", GenerateCourseReportArgs, _generate_course_report),
    "create_booking": ToolDef("create_booking", "创建预约订单，必须提供用户确认令牌", CreateBookingArgs, _create_booking, high_risk=True),
    "request_confirmation": ToolDef("request_confirmation", "为写入操作申请用户确认令牌", RequestConfirmationArgs, _request_confirmation),
}


def tool_specs(allowed: set[str] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": d.name,
                "description": d.description,
                "parameters": d.args_model.model_json_schema(),
            },
        }
        for d in TOOL_REGISTRY.values()
        if allowed is None or d.name in allowed
    ]


def execute_tool(name: str, raw_args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Whitelist -> Pydantic -> idempotency -> confirmation gate -> execute."""
    definition = TOOL_REGISTRY.get(name)
    if not definition:
        return {"error": {"code": "TOOL_NOT_WHITELISTED", "message": f"工具 {name} 不在白名单中，未执行"}}

    try:
        validated = definition.args_model(**raw_args)
    except (ValidationError, TypeError) as exc:
        return {"error": {"code": "INVALID_TOOL_ARGS", "message": str(exc)[:500]}}
    args = validated.model_dump()

    call_key = hashlib.sha256(
        f"{ctx.session_id}|{name}|{json.dumps(args, sort_keys=True, ensure_ascii=False)}".encode("utf-8")
    ).hexdigest()
    cached = ctx.conn.execute(
        'SELECT "outputJson" FROM "ToolInvocation" WHERE "callKey"=?', (call_key,)
    ).fetchone()
    if cached:
        try:
            payload = json.loads(cached["outputJson"])
            return {"cached": True, **payload, "status": "cached"}
        except json.JSONDecodeError:
            pass

    started = time.time()
    try:
        result = definition.func(args, ctx)
        status = "success"
    except ToolError as exc:
        result = {"error": {"code": exc.code, "message": exc.message}}
        status = "failed"
    except ApiError as exc:
        result = {"error": {"code": exc.code, "message": exc.message}}
        status = "failed"
    except Exception as exc:  # noqa: BLE001 - never let a tool crash the whole run
        result = {"error": {"code": "TOOL_EXECUTION_ERROR", "message": str(exc)[:500]}}
        status = "failed"

    ctx.conn.execute(
        'INSERT OR IGNORE INTO "ToolInvocation" '
        '("id","sessionId","callKey","toolName","inputJson","outputJson","createdAt") VALUES (?,?,?,?,?,?,?)',
        (db.new_id("ti"), ctx.session_id, call_key, name,
         json.dumps(args, ensure_ascii=False), json.dumps(result, ensure_ascii=False, default=str), db.now_ms()),
    )
    return {**result, "durationMs": int((time.time() - started) * 1000), "status": status}


# ------------------------------------------------------------------ offline FC driver
def _demo_payload(ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "child_id": ctx.get("childId") or "",
        "service_id": ctx.get("serviceId") or "svc_basketball",
        "start_at": ctx.get("startAt") or "2026-11-14T09:00:00+08:00",
        "end_at": ctx.get("endAt") or "2026-11-14T10:00:00+08:00",
    }


class StarFitMock:
    """Offline model that emits real tool_calls; the backend executes them normally."""

    @staticmethod
    def _call(index: int, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f"sf_mock_call_{index}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
        }

    @staticmethod
    def _plan(ctx: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        message = ctx.get("message", "")
        cid = ctx.get("childId") or ""
        conf = ctx.get("confirmationId")
        steps: list[tuple[str, dict[str, Any]]] = []

        if any(k in message for k in ("预约", "下单", "订课", "帮我约", "确认预约")):
            if conf:
                pending = next(
                    (p for p in ctx.get("state", {}).get("pendingConfirmations", []) if p.get("id") == conf and not p.get("used")),
                    None,
                )
                payload = (pending or {}).get("payload") or _demo_payload(ctx)
                steps.append(("create_booking", {**payload, "confirmation_id": conf}))
            else:
                steps.append(("request_confirmation", {
                    "action": "create_booking",
                    "summary": "创建预约订单（黑客松模拟支付，不产生真实扣款）",
                    "payload": _demo_payload(ctx),
                }))
        elif any(k in message for k in ("教练", "有空", "周末", "找一个", "找教练")):
            sport = ctx.get("sportType") or ("篮球基础" if "篮球" in message else None)
            steps.append(("search_coaches", {"sport_type": sport, "area": ctx.get("area"), "available_on": ctx.get("availableOn")}))
            if ctx.get("coachId"):
                steps.append(("get_available_slots", {"coach_id": ctx["coachId"]}))
        elif any(k in message for k in ("报告", "反馈", "总结", "课后")):
            steps.append(("get_training_history", {"child_id": cid, "limit": 3}))
            if ctx.get("bookingId"):
                steps.append(("generate_course_report", {"booking_id": ctx["bookingId"], "confirmation_id": conf}))
        elif any(k in message for k in ("星", "成长", "星图", "进度")):
            steps.append(("get_growth_progress", {"child_id": cid}))
        else:
            steps.append(("get_child_profile", {"child_id": cid}))
            steps.append(("get_training_history", {"child_id": cid, "limit": 3}))
            steps.append(("search_exercises", {"keyword": ctx.get("keyword"), "age": ctx.get("age")}))
            steps.append(("generate_training_plan", {"child_id": cid, "goal": ctx.get("goal") or "提升协调性", "weeks": 4}))
        return steps

    @staticmethod
    def _final_text(messages: list[dict[str, Any]]) -> str:
        results: list[dict[str, Any]] = []
        for m in messages:
            if m.get("role") == "tool":
                try:
                    results.append(json.loads(m.get("content", "{}")))
                except json.JSONDecodeError:
                    pass
        if any(r.get("error") for r in results):
            for r in results:
                if r.get("error"):
                    return f"这一步没能完成：{r['error']['message']}。{SAFETY_NOTE}"
        if any("confirmationId" in r for r in results):
            return "我已整理好要执行的操作，但需要您明确确认。请回传上一步返回的 confirmationId，我再继续。"
        if any("booking" in r for r in results):
            return "预约订单已创建（模拟支付），教练接单后即可开课。成长星星会在课程真实完成后发放。"
        if any("starTotal" in r for r in results):
            r = next(x for x in results if "starTotal" in x)
            return f"孩子目前已点亮 {r['starTotal']} 颗成长星星，完成真实课程或家庭任务后会继续增加。{SAFETY_NOTE}"
        if any("report" in str(r) or "course" in r for r in results):
            return "课后反馈草稿已基于教练提交的真实训练记录生成，确认后才会保存。"
        if any("coaches" in r for r in results):
            return "已按条件筛出教练及真实可预约档期，确认后我可以帮您创建预约。"
        if any("weeks" in r for r in results):
            return "已结合儿童档案、真实训练记录和动作知识库生成结构化运动建议，具体动作与安全提示见工具结果。"
        return f"已完成本轮处理（{len(results)} 个工具调用）。{SAFETY_NOTE}"

    @classmethod
    def chat(cls, messages: list[dict[str, Any]], tools: list[dict[str, Any]], context: dict[str, Any]) -> LLMResponse:
        if messages and messages[-1].get("role") == "tool":
            return LLMResponse(
                content=cls._final_text(messages), tool_calls=[],
                usage={"prompt_tokens": 180, "completion_tokens": 60, "total_tokens": 240},
                model="mock-starfit",
            )
        steps = cls._plan(context)
        calls = [cls._call(i + 1, name, args) for i, (name, args) in enumerate(steps)]
        return LLMResponse(
            content=None, tool_calls=calls,
            usage={"prompt_tokens": 200 + len(calls) * 25, "completion_tokens": 70,
                   "total_tokens": 270 + len(calls) * 25},
            model="mock-starfit",
        )


def _chat(
    llm: BailianClient,
    messages: list[dict[str, Any]],
    context: dict[str, Any],
    allowed_tools: set[str] | None = None,
    model_override: str | None = None,
) -> LLMResponse:
    if llm.mode == "mock":
        return StarFitMock.chat(messages, tool_specs(allowed_tools), context)
    return llm.chat(messages, tool_specs(allowed_tools), context, model_override=model_override)


# ------------------------------------------------------------------ orchestration
def _save_message(conn: Any, session_id: str, role: str, content: str,
                  tool_calls: Any = None, tool_results: Any = None) -> None:
    conn.execute(
        'INSERT INTO "sf_agent_message" '
        '("id","sessionId","role","content","toolCallsJson","toolResultsJson","createdAt") VALUES (?,?,?,?,?,?,?)',
        (db.new_id("am"), session_id, role, content,
         json.dumps(tool_calls, ensure_ascii=False) if tool_calls is not None else None,
         json.dumps(tool_results, ensure_ascii=False) if tool_results is not None else None,
         db.now_ms()),
    )


def _resolve_session(conn: Any, user: dict[str, Any], payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    session_id = payload.get("sessionId")
    if session_id:
        row = conn.execute(
            'SELECT * FROM "sf_agent_session" WHERE "id"=? AND "userId"=?', (session_id, user["id"])
        ).fetchone()
        if not row:
            raise ApiError(404, "SESSION_NOT_FOUND", f"会话 {session_id} 不存在或不属于当前用户")
        return session_id, json.loads(row["stateJson"] or "{}")
    session_id = db.new_id("as")
    now = db.now_ms()
    conn.execute(
        'INSERT INTO "sf_agent_session" '
        '("id","userId","childId","title","stateJson","createdAt","updatedAt") VALUES (?,?,?,?,?,?,?)',
        (session_id, user["id"], payload.get("childId"), str(payload.get("message", ""))[:40],
         json.dumps({}, ensure_ascii=False), now, now),
    )
    return session_id, {}


def run_chat(llm: BailianClient, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "")).strip()
    if not message:
        raise ApiError(400, "VALIDATION_ERROR", "message 必填")
    confirmation_id = payload.get("confirmationId")
    context = dict(payload.get("context") or {})
    context.update(
        {
            "message": message,
            "childId": payload.get("childId") or context.get("childId"),
            "confirmationId": confirmation_id,
            "role": user["role"],
        }
    )

    with db.get_conn() as conn:
        session_id, state = _resolve_session(conn, user, payload)
        _save_message(conn, session_id, "user", message)
        history = conn.execute(
            'SELECT * FROM "sf_agent_message" WHERE "sessionId"=? ORDER BY "createdAt","id"',
            (session_id,),
        ).fetchall()

    context_hint = (
        f"当前登录用户：{user.get('name') or user['id']}"
        f"（角色 {user['role']}，id={user['id']}）。"
    )
    if payload.get("childId"):
        context_hint += f"本轮指定儿童档案 ID：{payload['childId']}。"
    else:
        context_hint += "用户未指定儿童档案；调用 get_child_profile 时 child_id 可留空以读取该家长默认档案。"
    if confirmation_id:
        context_hint += f"本轮用户已回传 confirmationId={confirmation_id}，可用于需要确认的写入操作。"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_hint},
    ]
    for h in history:
        if h["role"] in ("user", "assistant") and h["content"]:
            messages.append({"role": h["role"], "content": h["content"]})

    tool_log: list[dict[str, Any]] = []
    pending_confirmation: dict[str, Any] | None = None
    stats = TokenStats()
    rounds = 0
    reply = ""
    last_model = llm.primary_model
    run_started = time.time()

    while rounds < settings.MAX_TOOL_ROUNDS:
        context["state"] = state
        response = _chat(llm, messages, context)
        stats.add(response.usage, response.model)
        last_model = response.model

        if not response.tool_calls:
            reply = response.content or f"已完成本轮处理（{len(tool_log)} 个工具调用）。{SAFETY_NOTE}"
            break

        messages.append(
            {"role": "assistant", "content": None, "tool_calls": response.tool_calls}
        )
        tool_results: list[dict[str, Any]] = []
        for call in response.tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                raw = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                raw = {}
            with db.transaction() as conn:
                ctx = ToolContext(
                    conn=conn, user=user, session_id=session_id, state=state,
                    confirmation_id=confirmation_id, context=context,
                )
                result = execute_tool(name, raw, ctx)
            tool_results.append({"tool_call_id": call.get("id"), "name": name, "result": result})
            tool_log.append({"name": name, "arguments": raw, "status": result.get("status"), "result": result})
            if name == "request_confirmation" and "confirmationId" in result:
                pending_confirmation = {
                    "confirmationId": result["confirmationId"],
                    "action": result["action"],
                    "summary": result["summary"],
                }
            messages.append(
                {"role": "tool", "tool_call_id": call.get("id"),
                 "content": json.dumps(result, ensure_ascii=False, default=str)}
            )
        rounds += 1
        with db.get_conn() as conn:
            _save_message(conn, session_id, "assistant", "", response.tool_calls, tool_results)

    if not reply:
        reply = f"已达到工具调用轮次上限（{settings.MAX_TOOL_ROUNDS}），请补充信息后继续。{SAFETY_NOTE}"

    with db.get_conn() as conn:
        _save_message(conn, session_id, "assistant", reply)
        conn.execute(
            'UPDATE "sf_agent_session" SET "stateJson"=?, "updatedAt"=?, "childId"=COALESCE(?, "childId") WHERE "id"=?',
            (json.dumps(state, ensure_ascii=False, default=str), db.now_ms(),
             payload.get("childId"), session_id),
        )

    return {
        "sessionId": session_id,
        "reply": reply,
        "llmMode": llm.mode,
        "model": last_model,
        "fcSupported": llm.fc_supported,
        "mode": "function_calling",
        "toolRounds": rounds,
        "toolCalls": tool_log,
        "pendingConfirmation": pending_confirmation,
        "tokenUsage": stats.as_dict(),
        "latencyMs": int((time.time() - run_started) * 1000),
        "childId": payload.get("childId"),
        "disclaimer": SAFETY_NOTE,
    }


def get_session(conn: Any, user: dict[str, Any], session_id: str) -> dict[str, Any]:
    row = conn.execute('SELECT * FROM "sf_agent_session" WHERE "id"=?', (session_id,)).fetchone()
    if not row:
        raise ApiError(404, "SESSION_NOT_FOUND", f"会话 {session_id} 不存在")
    if row["userId"] != user["id"] and user["role"] != "ADMIN":
        raise ApiError(403, "FORBIDDEN", "只能查看自己的会话")
    messages = conn.execute(
        'SELECT * FROM "sf_agent_message" WHERE "sessionId"=? ORDER BY "createdAt","id"', (session_id,)
    ).fetchall()
    return {
        "sessionId": row["id"],
        "userId": row["userId"],
        "childId": row["childId"],
        "title": row["title"],
        "createdAt": db.ms_to_iso(row["createdAt"]),
        "updatedAt": db.ms_to_iso(row["updatedAt"]),
        "state": json.loads(row["stateJson"] or "{}"),
        "messages": [
            {
                "id": m["id"],
                "role": m["role"],
                "content": m["content"],
                "toolCalls": json.loads(m["toolCallsJson"]) if m["toolCallsJson"] else None,
                "toolResults": json.loads(m["toolResultsJson"]) if m["toolResultsJson"] else None,
                "createdAt": db.ms_to_iso(m["createdAt"]),
            }
            for m in messages
        ],
    }
