"""Backend Python functions exposed to Bailian through Function Calling.

Safety properties:
  * Whitelist: only names in TOOL_REGISTRY can ever be executed.
  * Pydantic: every tool's arguments are validated with extra="forbid".
  * DB pricing: amounts are read from price_item and computed in Python.
  * Booking conflict: checked inside BEGIN IMMEDIATE before insert.
  * Confirmation gate: business-committing tools need a token that only the
    HTTP client (the user) can mark as confirmed; the model cannot mint it.
  * Idempotency: (session, tool, args) is unique in ToolInvocation; repeats
    return the cached result instead of creating another record.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import ValidationError

from . import db
from .models import (
    BusinessCalculateQuoteArgs,
    BusinessGetPriceListArgs,
    OperationsCheckAvailabilityArgs,
    OperationsCreateBookingArgs,
    OperationsCreateFollowupDraftArgs,
    PlanCreateTrainingPlanArgs,
    ReceptionAskMissingInfoArgs,
    ReceptionGetLeadArgs,
    ReceptionUpdateLeadFieldsArgs,
    SharedRequestConfirmationArgs,
    StrictModel,
)

MEDICAL_DISCLAIMER = (
    "本方案仅为一般儿童体育活动建议，不构成医疗诊断、康复治疗或任何医学判断；"
    "如孩子有伤病或特殊健康状况，请咨询专业医生。"
)


class ToolError(Exception):
    def __init__(self, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass
class ToolContext:
    session_id: str
    lead_id: str
    state: dict[str, Any]
    confirmation_id: str | None


@dataclass
class ToolDef:
    name: str
    employee: str
    description: str
    args_model: type[StrictModel]
    func: Callable[[dict[str, Any], ToolContext], dict[str, Any]]
    high_risk: bool = False


# ------------------------------------------------------------------ helpers
def _insert_message(conn, lead_id: str, role: str, content: str) -> str:
    message_id = db.new_id("m")
    conn.execute(
        'INSERT INTO "Message" ("id","leadId","role","content","createdAt") VALUES (?,?,?,?,?)',
        (message_id, lead_id, role, content, db.now_ms()),
    )
    return message_id


def _get_lead(conn, lead_id: str) -> dict[str, Any]:
    row = conn.execute('SELECT * FROM "Lead" WHERE "id" = ?', (lead_id,)).fetchone()
    if not row:
        raise ToolError("LEAD_NOT_FOUND", f"客户 {lead_id} 不存在")
    return dict(row)


def heuristic_extract(text: str) -> dict[str, Any]:
    """Deterministic field extraction for the offline demo / fallback driver."""
    age_m = re.search(r"(\d{1,2})\s*(?:岁|周岁)", text)
    time_m = re.search(
        r"(周[一二三四五六日天1-7]|周末|平时|每天|上午|下午|晚上|放学后)[^，。,.!！\n]{0,12}", text
    )
    goals = ["跳绳", "篮球", "足球", "体能", "协调性", "长高", "增强体质", "感统", "游泳", "跑步", "羽毛球", "平衡", "专注力", "柔韧", "力量"]
    goal = next((g for g in goals if g in text), None)
    exp_m = re.search(r"(零基础|没基础|没有基础|有基础|学过|练过|初级|进阶)", text)
    loc_m = re.search(r"(?:住在|地址是|地址|小区|位于)([^，。,.!！\n]{1,20})", text)
    return {
        "child_age": min(18, max(1, int(age_m.group(1)))) if age_m else None,
        "goal": goal,
        "experience": exp_m.group(1) if exp_m else None,
        "available_time": time_m.group(0).strip() if time_m else None,
        "location": loc_m.group(1).strip() if loc_m else None,
    }


# ------------------------------------------------------------------ tools
def reception_get_lead(args: dict, ctx: ToolContext) -> dict[str, Any]:
    with db.get_conn() as conn:
        lead = _get_lead(conn, args["lead_id"])
        messages = [
            dict(r)
            for r in conn.execute(
                'SELECT "role","content","createdAt" FROM "Message" WHERE "leadId" = ? ORDER BY "createdAt" DESC LIMIT 8',
                (args["lead_id"],),
            )
        ]
    return {"lead": lead, "recentMessages": messages}


def reception_update_lead_fields(args: dict, ctx: ToolContext) -> dict[str, Any]:
    lead_id = args["lead_id"]
    with db.get_conn() as conn:
        lead = _get_lead(conn, lead_id)
        conn.execute(
            'UPDATE "Lead" SET "childAge" = ?, "goal" = ?, "location" = ?, "updatedAt" = ? WHERE "id" = ?',
            (
                args.get("child_age") if args.get("child_age") is not None else lead["childAge"],
                args.get("goal") if args.get("goal") is not None else lead["goal"],
                args.get("location") if args.get("location") is not None else lead["location"],
                db.now_ms(),
                lead_id,
            ),
        )
        # experience / availableTime have no dedicated column in the existing
        # Prisma schema; persist them as a structured Message instead of
        # altering an existing table.
        _insert_message(
            conn,
            lead_id,
            "system",
            json.dumps({"type": "extracted_fields", **args}, ensure_ascii=False),
        )
        updated = _get_lead(conn, lead_id)
    return {"updated": True, "lead": updated, "storedExtraction": args}


def reception_ask_missing_info(args: dict, ctx: ToolContext) -> dict[str, Any]:
    labels = {
        "childAge": "孩子的年龄",
        "goal": "想训练的运动目标",
        "availableTime": "方便上课的时间",
    }
    question = (
        "您好，感谢咨询！为了给孩子安排合适的上门训练，还想确认一下："
        + "、".join(labels.get(f, f) for f in fields)
        + "。您方便时回复即可。"
    )
    return {"asked": True, "missingFields": fields, "question": question}


def plan_create_training_plan(args: dict, ctx: ToolContext) -> dict[str, Any]:
    age, goal, experience = args["age"], args["goal"], args["experience"]
    themes = ["基础动作与兴趣建立", "协调与平衡进阶", "目标技能专项练习", "综合巩固与成果展示"]
    weeks = [
        {
            "week": i + 1,
            "theme": f"第 {i + 1} 周：{theme}（{goal}）",
            "warmup": "5-8 分钟动态拉伸、关节激活与轻松追逐跑",
            "mainTraining": f"围绕「{goal}」的基础动作分解练习，每组 8-10 次、共 3 组，强度按 {age} 岁与「{experience}」调整",
            "game": "趣味接力或标志桶游戏，控制对抗强度",
            "cooldown": "5 分钟慢走 + 静态拉伸 + 呼吸放松",
            "homework": f"每天约 10 分钟亲子练习：{goal} 相关基础动作",
        }
        for i, theme in enumerate(themes)
    ]
    plan_id = db.new_id("pl")
    with db.get_conn() as conn:
        _get_lead(conn, args["lead_id"])
        conn.execute(
            'INSERT INTO "TrainingPlan" '
            '("id","leadId","age","goal","experience","weeksJson","disclaimer","createdAt") '
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                plan_id,
                args["lead_id"],
                age,
                goal,
                experience,
                json.dumps(weeks, ensure_ascii=False),
                MEDICAL_DISCLAIMER,
                db.now_ms(),
            ),
        )
    return {
        "planId": plan_id,
        "weeks": weeks,
        "disclaimer": MEDICAL_DISCLAIMER,
        "note": "仅一般体育活动建议，不含医疗或康复判断",
    }


def business_get_price_list(args: dict, ctx: ToolContext) -> dict[str, Any]:
    with db.get_conn() as conn:
        prices = db.list_prices(conn)
    return {
        "source": "database:price_item",
        "currency": "CNY",
        "items": prices,
        "note": "报价金额必须以此表中的 unitPriceCents 为准，由 Python 计算",
    }


def business_calculate_quote(args: dict, ctx: ToolContext) -> dict[str, Any]:
    lead_id = args["lead_id"]
    with db.transaction() as conn:
        _get_lead(conn, lead_id)
        price = db.get_price(conn, args["package_type"])
        if not price:
            raise ToolError("PRICE_NOT_FOUND", f"数据库中没有套餐 {args['package_type']} 的价格")
        unit = int(price["unitPriceCents"])
        quantity = int(args["quantity"])
        amount = unit * quantity  # deterministic, Python-side, never from the model
        total = amount

        # Business-level idempotency: identical quote for this lead is reused.
        existing = conn.execute(
            'SELECT "id","totalCents" FROM "Quote" WHERE "leadId" = ? AND "totalCents" = ? '
            'ORDER BY "createdAt" DESC LIMIT 1',
            (lead_id, total),
        ).fetchone()
        if existing:
            items = [dict(r) for r in conn.execute('SELECT * FROM "QuoteItem" WHERE "quoteId" = ?', (existing["id"],))]
            return {"quoteId": existing["id"], "totalCents": total, "items": items, "reused": True}

        quote_id = db.new_id("q")
        item_id = db.new_id("qi")
        conn.execute(
            'INSERT INTO "Quote" ("id","leadId","currency","totalCents","note","createdAt") VALUES (?,?,?,?,?,?)',
            (quote_id, lead_id, "CNY", total, f"后端按数据库价目表计算：{price['name']} × {quantity}", db.now_ms()),
        )
        conn.execute(
            'INSERT INTO "QuoteItem" ("id","quoteId","name","quantity","unitPriceCents","amountCents") '
            "VALUES (?,?,?,?,?,?)",
            (item_id, quote_id, price["name"], quantity, unit, amount),
        )
        conn.execute(
            'UPDATE "Lead" SET "status" = ?, "updatedAt" = ? WHERE "id" = ? AND "status" IN (\'new\',\'consulting\')',
            ("quoted", db.now_ms(), lead_id),
        )
        items = [dict(r) for r in conn.execute('SELECT * FROM "QuoteItem" WHERE "quoteId" = ?', (quote_id,))]
    return {
        "quoteId": quote_id,
        "packageType": args["package_type"],
        "unitPriceCents": unit,
        "quantity": quantity,
        "totalCents": total,
        "totalYuan": f"{total / 100:.2f}",
        "items": items,
        "reused": False,
        "computedBy": "python:db_price * quantity",
    }


def operations_check_availability(args: dict, ctx: ToolContext) -> dict[str, Any]:
    start, end = db.iso_to_ms(args["start_at"]), db.iso_to_ms(args["end_at"])
    if end <= start:
        raise ToolError("INVALID_TIME_RANGE", "endAt 必须晚于 startAt")
    with db.get_conn() as conn:
        conflicts = [
            dict(r)
            for r in conn.execute(
                'SELECT "id","leadId","startAt","endAt","status" FROM "Booking" '
                'WHERE "status" IN (\'pending\',\'confirmed\') AND "startAt" < ? AND "endAt" > ?',
                (end, start),
            )
        ]
    return {
        "available": len(conflicts) == 0,
        "startAtMs": start,
        "endAtMs": end,
        "conflicts": conflicts,
    }


def operations_create_booking(args: dict, ctx: ToolContext) -> dict[str, Any]:
    lead_id = args["lead_id"]
    start, end = db.iso_to_ms(args["start_at"]), db.iso_to_ms(args["end_at"])
    if end <= start:
        raise ToolError("INVALID_TIME_RANGE", "endAt 必须晚于 startAt")

    with db.transaction() as conn:
        _get_lead(conn, lead_id)
        conflicts = conn.execute(
            'SELECT "id" FROM "Booking" WHERE "status" IN (\'pending\',\'confirmed\') '
            'AND "startAt" < ? AND "endAt" > ?',
            (end, start),
        ).fetchall()
        if conflicts:
            raise ToolError(
                "BOOKING_CONFLICT",
                "该时间段已有预约，请另选时间",
                {"conflictingIds": [r["id"] for r in conflicts]},
            )
        existing = conn.execute(
            'SELECT * FROM "Booking" WHERE "leadId" = ? AND "startAt" = ? AND "endAt" = ? '
            'AND "status" IN (\'pending\',\'confirmed\') LIMIT 1',
            (lead_id, start, end),
        ).fetchone()
        if existing:
            return {"bookingId": existing["id"], "status": existing["status"], "reused": True}

        booking_id = db.new_id("b")
        conn.execute(
            'INSERT INTO "Booking" ("id","leadId","startAt","endAt","status","note","createdAt") '
            "VALUES (?,?,?,?,?,?,?)",
            (booking_id, lead_id, start, end, "pending", args.get("note"), db.now_ms()),
        )
    return {
        "bookingId": booking_id,
        "startAtMs": start,
        "endAtMs": end,
        "status": "pending",
        "reused": False,
        "note": "用户确认令牌已授权创建；状态保持 pending，最终 confirmed 仍按既有业务规则单独确认",
    }


def operations_create_followup_draft(args: dict, ctx: ToolContext) -> dict[str, Any]:
    with db.get_conn() as conn:
        lead = _get_lead(conn, args["lead_id"])
    body = f"{lead['parentName']}您好，之前的课程方案和报价已备好，有任何问题随时回复我就好，不着急决定。"
    with db.get_conn() as conn:
        message_id = _insert_message(
            conn,
            args["lead_id"],
            "draft",
            json.dumps({"type": "followup_draft", "channel": args["channel"], "body": body, "doNotDisturb": True}, ensure_ascii=False),
        )
    return {"draftMessageId": message_id, "body": body, "sent": False, "requiresHumanConfirmation": True}


def shared_request_confirmation(args: dict, ctx: ToolContext) -> dict[str, Any]:
    token = db.new_id("cf")
    record = {
        "action": args["action"],
        "summary": args["summary"],
        "confirmed": False,
        "consumed": False,
        "createdAt": db.now_ms(),
    }
    ctx.state.setdefault("confirmations", {})[token] = record
    ctx.state["pendingConfirmation"] = {"token": token, "action": args["action"], "summary": args["summary"]}
    with db.get_conn() as conn:
        db.save_session(conn, ctx.session_id, ctx.state)
    return {
        "token": token,
        "action": args["action"],
        "summary": args["summary"],
        "requiresUserConfirmation": True,
        "note": "模型不能自行确认；必须由客户端在下次 /api/v1/ai/chat 请求中回传 confirmationId",
    }


# ------------------------------------------------------------------ registry
TOOL_DEFS: list[ToolDef] = [
    ToolDef("reception_get_lead", "接待员工", "读取客户档案与最近咨询记录", ReceptionGetLeadArgs, reception_get_lead),
    ToolDef("reception_update_lead_fields", "接待员工", "把家长消息里明确提供的年龄/目标/经验/时间/位置写入客户档案，未知字段不填", ReceptionUpdateLeadFieldsArgs, reception_update_lead_fields),
    ToolDef("reception_ask_missing_info", "接待员工", "关键信息缺失时生成追问话术（由编排器统一写入消息记录）", ReceptionAskMissingInfoArgs, reception_ask_missing_info),
    ToolDef("plan_create_training_plan", "方案员工", "按年龄/目标/基础生成四周一般体育活动方案并入库", PlanCreateTrainingPlanArgs, plan_create_training_plan),
    ToolDef("business_get_price_list", "商务员工", "从数据库读取当前可配置价目表", BusinessGetPriceListArgs, business_get_price_list),
    ToolDef("business_calculate_quote", "商务员工", "读取数据库价格并由 Python 计算金额，生成报价单（需用户确认令牌）", BusinessCalculateQuoteArgs, business_calculate_quote, high_risk=True),
    ToolDef("operations_check_availability", "运营员工", "查询指定时段是否已有冲突预约", OperationsCheckAvailabilityArgs, operations_check_availability),
    ToolDef("operations_create_booking", "运营员工", "检测冲突后创建待确认预约（需用户确认令牌）", OperationsCreateBookingArgs, operations_create_booking, high_risk=True),
    ToolDef("operations_create_followup_draft", "运营员工", "生成跟进话术草稿，仅保存不发送", OperationsCreateFollowupDraftArgs, operations_create_followup_draft),
    ToolDef("shared_request_confirmation", "共享", "为高风险/业务承诺动作申请用户确认令牌，不创建任何业务记录", SharedRequestConfirmationArgs, shared_request_confirmation),
]

TOOL_REGISTRY: dict[str, ToolDef] = {t.name: t for t in TOOL_DEFS}


def tool_specs() -> list[dict[str, Any]]:
    """OpenAI `tools` payload, generated from the same Pydantic models used for validation."""
    specs = []
    for t in TOOL_DEFS:
        schema = t.args_model.model_json_schema()
        schema.setdefault("additionalProperties", False)
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": f"[{t.employee}] {t.description}",
                    "parameters": schema,
                },
            }
        )
    return specs


# ------------------------------------------------------------------ executor
def execute_tool(name: str, raw_args: Any, ctx: ToolContext) -> dict[str, Any]:
    started = time.time()

    def result(ok: bool, payload: Any, code: str | None = None, dedup: bool = False) -> dict[str, Any]:
        return {
            "ok": ok,
            "tool": name,
            "employee": TOOL_REGISTRY[name].employee if name in TOOL_REGISTRY else "unknown",
            "code": code,
            "result": payload if ok else None,
            "error": payload if not ok else None,
            "deduplicated": dedup,
            "durationMs": int((time.time() - started) * 1000),
        }

    definition = TOOL_REGISTRY.get(name)
    if definition is None:
        return result(
            False,
            {"message": f"工具 {name} 不在白名单中，拒绝执行", "allowed": sorted(TOOL_REGISTRY)},
            "TOOL_NOT_WHITELISTED",
        )

    if isinstance(raw_args, str):
        try:
            args: Any = json.loads(raw_args)
        except json.JSONDecodeError as exc:
            return result(False, {"message": f"工具参数不是合法 JSON: {exc}"}, "INVALID_TOOL_ARGS_JSON")
    elif isinstance(raw_args, dict):
        args = raw_args
    else:
        return result(False, {"message": "工具参数必须是对象或 JSON 字符串"}, "INVALID_TOOL_ARGS")

    try:
        validated = definition.args_model.model_validate(args)
    except ValidationError as exc:
        return result(
            False,
            {"message": "工具参数未通过 Pydantic 校验", "issues": exc.errors()},
            "INVALID_TOOL_ARGS",
        )
    vargs = validated.model_dump(exclude_none=True)

    # ---- idempotency (prevents duplicate records on repeated tool calls) ----
    canonical = json.dumps(vargs, sort_keys=True, ensure_ascii=False)
    call_key = hashlib.sha256(f"{ctx.session_id}|{name}|{canonical}".encode("utf-8")).hexdigest()
    with db.get_conn() as conn:
        prior = db.lookup_invocation(conn, call_key)
    if prior:
        return result(True, json.loads(prior["outputJson"]), dedup=True)

    # ---- explicit user confirmation gate ----
    if definition.high_risk:
        token = vargs.get("confirmation_id", "")
        confirmation = ctx.state.get("confirmations", {}).get(token)
        if not confirmation:
            return result(False, {"message": "缺少有效的用户确认令牌", "tool": name}, "CONFIRMATION_REQUIRED")
        if not confirmation.get("confirmed"):
            return result(False, {"message": "该动作尚未获得用户确认", "tool": name}, "CONFIRMATION_NOT_GRANTED")
        if confirmation.get("consumed"):
            return result(False, {"message": "确认令牌已被使用", "tool": name}, "CONFIRMATION_ALREADY_USED")
        expected = "calculate_quote" if name == "business_calculate_quote" else "create_booking"
        if confirmation.get("action") != expected:
            return result(False, {"message": "确认令牌与动作不匹配", "tool": name}, "CONFIRMATION_ACTION_MISMATCH")

    try:
        payload = definition.func(vargs, ctx)
    except ToolError as exc:
        return result(False, {"message": exc.message, "details": exc.details}, exc.code)
    except Exception as exc:  # noqa: BLE001 - surfaced to the model, never crashes the run
        return result(False, {"message": f"工具执行异常: {exc}"}, "TOOL_EXECUTION_FAILED")

    if definition.high_risk:
        confirmation = ctx.state["confirmations"][vargs["confirmation_id"]]
        confirmation["consumed"] = True
        if (ctx.state.get("pendingConfirmation") or {}).get("token") == vargs["confirmation_id"]:
            ctx.state["pendingConfirmation"] = None
        with db.get_conn() as conn:
            db.save_session(conn, ctx.session_id, ctx.state)

    with db.get_conn() as conn:
        db.store_invocation(conn, ctx.session_id, call_key, name, vargs, payload)
    return result(True, payload)
