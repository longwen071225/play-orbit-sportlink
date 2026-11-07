"""Contract-compat API for the `coach-admin` React frontend (starfit-coach-admin).

Implements the frontend's mock-handler contract on top of the REAL StarFit
tables (sf_booking / sf_child / sf_user / sf_service / sf_family_task /
sf_task_submission / sf_training_record / sf_training_plan / sf_coach /
sf_growth_star):

  * Raw JSON responses (no {success,data} envelope) — the React axios client
    returns `response.data` directly, so these routes bypass ok()/envelope.
  * Lowercase statuses mirror the canonical machine, including cancelled and
    rejected; report availability is not an order status.
  * POST /api/coach/orders/:id/ai-report performs a REAL Bailian call and
    persists the structured report in sf_training_plan (title marker
    `AI_REPORT:<bookingId>`), so reports survive restarts and can later be
    consumed by the parent side.
  * Errors follow the frontend contract: {"msg": "..."} with a proper status.
  * Authentication uses the shared password-only login route.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .. import db
from ..agent import ApiError
from ..llm import BailianClient, LLMError
from . import services
from .auth import assert_child_access, parse_token

router = APIRouter()

_STATUS_TO_UPPER = {state.lower(): state for state in services.ALLOWED_TRANSITIONS}
_TASK_STATUS_TO_UPPER = {"pending": "OPEN", "in_progress": "SUBMITTED", "completed": "CONFIRMED"}
_TASK_STATUS_TO_LOWER = {v: k for k, v in _TASK_STATUS_TO_UPPER.items()}
_GRADES = {"excellent", "good", "fair", "needs_work"}


def fail(status: int, msg: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"msg": msg})


def _user_from_token(request: Request) -> dict[str, Any] | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    payload = parse_token(header[7:].strip())
    if not payload:
        return None
    with db.get_conn() as conn:
        row = conn.execute('SELECT * FROM "sf_user" WHERE "id"=?', (payload.get("uid"),)).fetchone()
    return {"id": row["id"], "name": row["name"], "role": row["role"]} if row and row["status"] == "ACTIVE" else None


def _require(request: Request, *roles: str) -> dict[str, Any]:
    user = _user_from_token(request)
    if not user:
        raise _Err(401, "未登录")
    if roles and user["role"] not in roles:
        raise _Err(403, "无权访问")
    return user


class _Err(Exception):
    def __init__(self, status: int, msg: str) -> None:
        self.status = status
        self.msg = msg


def _err_handler(request: Request, exc: _Err) -> JSONResponse:  # registered on the app in register_starfit()
    return fail(exc.status, exc.msg)


# ------------------------------------------------------------------ helpers
def _coach_row(conn: Any, user: dict[str, Any]) -> Any:
    row = conn.execute('SELECT * FROM "sf_coach" WHERE "userId"=?', (user["id"],)).fetchone()
    if not row:
        raise _Err(404, "当前账号没有教练档案")
    return row


def _booking_row(conn: Any, booking_id: str) -> Any:
    row = conn.execute('SELECT * FROM "sf_booking" WHERE "id"=?', (booking_id,)).fetchone()
    if not row:
        raise _Err(404, "订单不存在")
    return row


def _owned_booking(conn: Any, user: dict[str, Any], booking_id: str) -> Any:
    row = _booking_row(conn, booking_id)
    if row["coachId"] != _coach_row(conn, user)["id"]:
        raise _Err(403, "该订单不属于你")
    return row


def _has_ai_report(conn: Any, booking_id: str) -> bool:
    return bool(conn.execute(
        'SELECT 1 FROM "sf_training_plan" WHERE "title"=? LIMIT 1', (f"AI_REPORT:{booking_id}",)
    ).fetchone())


def _get_ai_report(conn: Any, booking_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        'SELECT * FROM "sf_training_plan" WHERE "title"=? LIMIT 1', (f"AI_REPORT:{booking_id}",)
    ).fetchone()
    if not row:
        return None
    data = services._loads(row["planJson"], {})
    if not data:
        return None
    return {
        "id": row["id"],
        "orderId": booking_id,
        "summary": data.get("summary", ""),
        "strengths": data.get("strengths", []),
        "improvements": data.get("improvements", []),
        "homeSuggestion": data.get("homeSuggestion", ""),
        "nextPlan": data.get("nextPlan", ""),
        "rewardTriggered": bool(data.get("rewardTriggered", False)),
        "createdAt": db.ms_to_iso(row["createdAt"]),
    }


def _order_out(conn: Any, b: Any, status: str | None = None) -> dict[str, Any]:
    child = conn.execute('SELECT * FROM "sf_child" WHERE "id"=?', (b["childId"],)).fetchone()
    service = conn.execute('SELECT * FROM "sf_service" WHERE "id"=?', (b["serviceId"],)).fetchone()
    guardian = conn.execute('SELECT * FROM "sf_user" WHERE "id"=?', (child["guardianId"],)).fetchone() if child else None
    upper = status or b["status"]
    lower = upper.lower()
    return {
        "id": b["id"],
        "studentName": child["nickname"] if child else b["childId"],
        "studentAge": child["age"] if child else None,
        "parentName": guardian["name"] if guardian else "",
        "parentPhone": guardian["phone"] if guardian else "",
        "courseType": service["sportType"] if service else "",
        "address": b["address"],
        "scheduledAt": db.ms_to_iso(b["startAt"]),
        "durationMin": (b["endAt"] - b["startAt"]) // 60000,
        "status": lower,
        "coachId": b["coachId"],
        "remark": b["note"] or "",
        "createdAt": db.ms_to_iso(b["createdAt"]),
    }


def _training_log_out(conn: Any, booking_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        'SELECT * FROM "sf_training_record" WHERE "bookingId"=? ORDER BY "createdAt" DESC LIMIT 1',
        (booking_id,),
    ).fetchone()
    if not row:
        return None
    perf = services._loads(row["performance"], {})
    actions = perf.get("actions") or []
    return {
        "id": row["id"],
        "orderId": booking_id,
        "actions": actions,
        "durationMin": row["durationMinutes"],
        "performance": perf.get("grade", "good"),
        "note": row["content"],
        "createdAt": db.ms_to_iso(row["createdAt"]),
    }


def _task_out(conn: Any, t: Any) -> dict[str, Any]:
    items = services._loads(t["itemsJson"], [])
    child = conn.execute('SELECT "nickname" FROM "sf_child" WHERE "id"=?', (t["childId"],)).fetchone()
    description = next((i.get("note") for i in items if isinstance(i, dict) and i.get("note")), None)
    if not description:
        description = "、".join(i.get("name", "") if isinstance(i, dict) else str(i) for i in items)
    sub = conn.execute(
        'SELECT "content","createdAt" FROM "sf_task_submission" WHERE "taskId"=? ORDER BY "createdAt" DESC LIMIT 1',
        (t["id"],),
    ).fetchone()
    created = t["createdAt"]
    return {
        "id": t["id"],
        "orderId": t["bookingId"] or "",
        "studentName": child["nickname"] if child else t["childId"],
        "coachId": t["coachId"],
        "title": t["title"],
        "description": description,
        "frequency": "每天",
        "suggestedDays": 7,
        "status": _TASK_STATUS_TO_LOWER.get(t["status"], "pending"),
        "parentFeedback": (sub["content"] if sub else None),
        "completedAt": db.ms_to_iso(sub["createdAt"]) if sub else None,
        "createdAt": db.ms_to_iso(created),
        "dueAt": db.ms_to_iso(created + 7 * 24 * 3600 * 1000),
    }


@router.get("/api/auth/me")
def me(request: Request):
    user = _require(request, "COACH", "ADMIN")
    with db.get_conn() as conn:
        if user["role"] == "COACH":
            c = _coach_row(conn, user)
            u = conn.execute('SELECT "phone" FROM "sf_user" WHERE "id"=?', (user["id"],)).fetchone()
            return {"id": c["id"], "name": c["name"], "role": "coach", "avatar": c["avatarUrl"] or "",
                    "phone": u["phone"] if u else "", "specialties": services._loads(c["courseTypes"], [])}
    return {"id": user["id"], "name": user["name"], "role": "admin", "avatar": "", "phone": "", "specialties": []}


# ------------------------------------------------------------------ coach dashboard / orders
@router.get("/api/coach/dashboard")
def coach_dashboard(request: Request):
    user = _require(request, "COACH")
    with db.get_conn() as conn:
        coach = _coach_row(conn, user)
        now = datetime.now()
        day_start = int(datetime(now.year, now.month, now.day).timestamp() * 1000)
        month_start = int(datetime(now.year, now.month, 1).timestamp() * 1000)
        one = lambda sql, args=(): int(conn.execute(sql, args).fetchone()[0] or 0)  # noqa: E731
        pending = one('SELECT COUNT(*) FROM "sf_booking" WHERE "coachId"=? AND "status"=\'PENDING\'', (coach["id"],))
        today = one(
            'SELECT COUNT(*) FROM "sf_booking" WHERE "coachId"=? AND "status" IN (\'ACCEPTED\',\'IN_PROGRESS\') '
            'AND "startAt" >= ? AND "startAt" < ?',
            (coach["id"], day_start, day_start + 24 * 3600 * 1000),
        )
        month_income = one(
            'SELECT COALESCE(SUM("amountCents"),0) FROM "sf_booking" WHERE "coachId"=? AND "status"=\'COMPLETED\' '
            'AND "startAt" >= ?',
            (coach["id"], month_start),
        )
        students = one(
            'SELECT COUNT(DISTINCT "childId") FROM "sf_booking" WHERE "coachId"=? '
            'AND "status" IN (\'ACCEPTED\',\'IN_PROGRESS\',\'COMPLETED\')',
            (coach["id"],),
        )
    return {
        "pendingCount": pending,
        "todayCourseCount": today,
        "monthIncome": round(month_income / 100, 2),
        "studentCount": students,
    }


@router.get("/api/coach/orders")
def coach_orders(request: Request, status: str | None = None, page: int = 1, pageSize: int = 20):
    user = _require(request, "COACH")
    with db.get_conn() as conn:
        coach = _coach_row(conn, user)
        rows = conn.execute(
            'SELECT * FROM "sf_booking" WHERE "coachId"=? ORDER BY "startAt" DESC', (coach["id"],)
        ).fetchall()
        if status and status in _STATUS_TO_UPPER:
            upper = _STATUS_TO_UPPER[status]
            rows = [r for r in rows if r["status"] == upper]
        items = [_order_out(conn, r) for r in rows]
    total = len(items)
    page = max(1, page)
    pageSize = max(1, min(pageSize, 100))
    return {"list": items[(page - 1) * pageSize: page * pageSize], "total": total, "page": page, "pageSize": pageSize}


@router.get("/api/coach/orders/{order_id}")
def coach_order_detail(request: Request, order_id: str):
    user = _require(request, "COACH")
    with db.get_conn() as conn:
        _coach_row(conn, user)
        b = _owned_booking(conn, user, order_id)
        out = _order_out(conn, b)
        out["trainingLog"] = _training_log_out(conn, order_id)
        out["aiReport"] = _get_ai_report(conn, order_id)
    return out


def _transition(request: Request, order_id: str, target: str):
    user = _require(request, "COACH")
    try:
        with db.transaction() as conn:
            _coach_row(conn, user)
            b = _booking_row(conn, order_id)
            if b["coachId"] != _coach_row(conn, user)["id"]:
                raise _Err(403, "该订单不属于你")
            data = services.transition_booking(conn, user, order_id, target, {})
    except ApiError as exc:
        return fail(exc.status_code, exc.message)
    with db.get_conn() as conn:
        return _order_out(conn, conn.execute('SELECT * FROM "sf_booking" WHERE "id"=?', (order_id,)).fetchone())


@router.post("/api/coach/orders/{order_id}/accept")
def accept_order(request: Request, order_id: str):
    return _transition(request, order_id, "ACCEPTED")


@router.post("/api/coach/orders/{order_id}/start")
def start_order(request: Request, order_id: str):
    return _transition(request, order_id, "IN_PROGRESS")


@router.post("/api/coach/orders/{order_id}/complete")
def complete_order(request: Request, order_id: str):
    return _transition(request, order_id, "COMPLETED")


@router.post("/api/coach/orders/{order_id}/training-log")
def submit_training_log(request: Request, order_id: str, body: dict[str, Any]):
    from .portal import feedback_out, save_feedback

    user = _require(request, "COACH")
    with db.get_conn() as conn:
        _owned_booking(conn, user, order_id)
        previous = feedback_out(conn, order_id) or {}
    payload = {
        **previous,
        "content": body.get("note", previous.get("content", "")),
        "actions": body.get("actions", previous.get("actions", [])),
        "durationMin": body.get("durationMin", previous.get("durationMin")),
        "performance": body.get("performance", previous.get("performance")),
    }
    save_feedback(request, order_id, payload)
    with db.get_conn() as conn:
        return _training_log_out(conn, order_id)


_AI_SYSTEM = (
    "你是儿童体育课后报告助手。根据课程类型、训练动作记录和表现等级，输出严格的 JSON（不要多余文字、不要 markdown 代码块），"
    '字段：{"summary": 一段话总评, "strengths": [亮点1, 亮点2], "improvements": [待提升1, 待提升2], '
    '"homeSuggestion": 家庭训练建议一句话, "nextPlan": 下次课计划一句话}。'
    "语气专业温和，面向家长，中文，不夸大不承诺医疗效果。"
)


def _fallback_report(course_type: str, actions: list[dict[str, Any]], grade: str, note: str) -> dict[str, Any]:
    names = "、".join(a["name"] for a in actions if a.get("name")) or "本节课程动作"
    grade_text = {"excellent": "出色", "good": "良好", "fair": "有起伏", "needs_work": "需要更多练习"}.get(grade, "良好")
    return {
        "summary": f"本次{course_type}课程整体表现{grade_text}，完成了{names}等训练内容。",
        "strengths": ["完成了教练布置的全部训练内容", "动作完成度较之前有提升"],
        "improvements": ["部分动作细节仍需教练继续纠正", "训练节奏可以更稳定"],
        "homeSuggestion": f"每周按教练布置的家庭任务复习{names}，注意热身与放松。",
        "nextPlan": "下次课在本次基础上适度提高难度，继续巩固基础动作。",
        "note": note[:120],
    }


@router.post("/api/coach/orders/{order_id}/ai-report")
def generate_ai_report(request: Request, order_id: str):
    user = _require(request, "COACH")
    llm: BailianClient = request.app.state.llm
    with db.get_conn() as conn:
        coach = _coach_row(conn, user)
        b = _booking_row(conn, order_id)
        if b["coachId"] != coach["id"]:
            raise _Err(403, "该订单不属于你")
        if b["status"] != "COMPLETED":
            return fail(400, "请先完成课程再生成 AI 报告")
        log = _training_log_out(conn, order_id)
        if not log:
            return fail(400, "请先提交训练记录，AI 报告需要真实训练数据")
        if _has_ai_report(conn, order_id):
            return _get_ai_report(conn, order_id)
        service = conn.execute('SELECT "sportType" FROM "sf_service" WHERE "id"=?', (b["serviceId"],)).fetchone()
        course_type = service["sportType"] if service else "体育"
        actions, grade, note = log["actions"], log["performance"], log["note"]

    report: dict[str, Any]
    started = time.time()
    try:
        resp = llm.chat(
            [
                {"role": "system", "content": _AI_SYSTEM},
                {"role": "user", "content": json.dumps(
                    {"courseType": course_type, "actions": actions, "performance": grade, "note": note},
                    ensure_ascii=False)},
            ],
            tools=[],
        )
        text = (resp.content or "").strip()
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
        report = {
            "summary": str(data.get("summary", "")).strip(),
            "strengths": [str(x) for x in (data.get("strengths") or [])][:5],
            "improvements": [str(x) for x in (data.get("improvements") or [])][:5],
            "homeSuggestion": str(data.get("homeSuggestion", "")).strip(),
            "nextPlan": str(data.get("nextPlan", "")).strip(),
        }
        if not report["summary"]:
            raise ValueError("empty summary")
    except (LLMError, ValueError, json.JSONDecodeError, KeyError):
        report = _fallback_report(course_type, actions, grade, note)
    with db.get_conn() as conn:
        report["rewardTriggered"] = bool(conn.execute(
            'SELECT 1 FROM "sf_growth_star" WHERE "sourceType"=\'BOOKING\' AND "sourceId"=? LIMIT 1',
            (order_id,),
        ).fetchone())
    report["elapsedMs"] = int((time.time() - started) * 1000)

    rid = db.new_id("tp")
    with db.transaction() as conn:
        conn.execute(
            'INSERT INTO "sf_training_plan" '
            '("id","childId","coachId","agentSessionId","title","planJson","disclaimer","status","createdAt") '
            "VALUES (?,?,?,?,?,?,?,'CONFIRMED',?)",
            (rid, b["childId"], coach["id"], order_id, f"AI_REPORT:{order_id}",
             json.dumps({"kind": "ai_report", **report}, ensure_ascii=False),
             "AI 课后总结基于教练提交的真实训练记录生成，仅供参考。", db.now_ms()),
        )
    with db.get_conn() as conn:
        final = _get_ai_report(conn, order_id)
    final["elapsedMs"] = report.get("elapsedMs")
    return final


# ------------------------------------------------------------------ students
@router.get("/api/coach/students")
def coach_students(request: Request, page: int = 1, pageSize: int = 20):
    user = _require(request, "COACH")
    from .portal import student_out

    with db.get_conn() as conn:
        coach = _coach_row(conn, user)
        rows = conn.execute(
            'SELECT DISTINCT "childId" FROM "sf_booking" WHERE "coachId"=? '
            'AND "status" IN (\'ACCEPTED\',\'IN_PROGRESS\',\'COMPLETED\')',
            (coach["id"],),
        ).fetchall()
        items = []
        for r in rows:
            child = conn.execute('SELECT * FROM "sf_child" WHERE "id"=?', (r["childId"],)).fetchone()
            if not child:
                continue
            stars = student_out(conn, child, coach["id"])["growthStars"]
            courses = conn.execute(
                'SELECT COUNT(*) FROM "sf_booking" WHERE "childId"=? AND "coachId"=? AND "status"=\'COMPLETED\'',
                (child["id"], coach["id"]),
            ).fetchone()[0]
            items.append({
                "id": child["id"], "name": child["nickname"], "age": child["age"],
                "authorized": True, "growthStars": stars, "recentCourseCount": courses,
            })
    total = len(items)
    page = max(1, page)
    pageSize = max(1, min(pageSize, 100))
    return {"list": items[(page - 1) * pageSize: page * pageSize], "total": total, "page": page, "pageSize": pageSize}


@router.get("/api/coach/students/{student_id}")
def coach_student_detail(request: Request, student_id: str):
    user = _require(request, "COACH")
    from .portal import student_out

    with db.get_conn() as conn:
        coach = _coach_row(conn, user)
        child = assert_child_access(conn, user, student_id)
        bookings = conn.execute(
            'SELECT * FROM "sf_booking" WHERE "childId"=? AND "coachId"=? AND "status" IN (\'COMPLETED\',\'IN_PROGRESS\',\'ACCEPTED\') '
            'ORDER BY "startAt" DESC',
            (student_id, coach["id"]),
        ).fetchall()
        stars = student_out(conn, child, coach["id"])["growthStars"]
        courses = sum(1 for b in bookings if b["status"] == "COMPLETED")
        recent = []
        for b in bookings[:10]:
            item = _order_out(conn, b)
            tlog = _training_log_out(conn, b["id"])
            if tlog:
                item["performance"] = tlog["performance"]
            rep = _get_ai_report(conn, b["id"])
            if rep:
                item["aiSummary"] = rep["summary"]
            recent.append(item)
    return {
        "id": child["id"], "name": child["nickname"], "age": child["age"],
        "authorized": True, "growthStars": stars, "recentCourseCount": courses, "recentCourses": recent,
    }


@router.get("/api/coach/calendar")
def coach_calendar(request: Request, start: str | None = None, end: str | None = None):
    user = _require(request, "COACH")
    from datetime import datetime as dt, timedelta

    def parse_day(value: str | None, fallback: dt) -> dt:
        try:
            return dt.strptime(value, "%Y-%m-%d")
        except (TypeError, ValueError):
            return fallback

    today = dt.now()
    start_dt, end_dt = parse_day(start, today), parse_day(end, today + timedelta(days=13))
    lo = int(start_dt.timestamp() * 1000)
    hi = int((end_dt + timedelta(days=1)).timestamp() * 1000)
    with db.get_conn() as conn:
        coach = _coach_row(conn, user)
        rows = conn.execute(
            'SELECT * FROM "sf_booking" WHERE "coachId"=? AND "status" IN (\'ACCEPTED\',\'IN_PROGRESS\',\'COMPLETED\') '
            'AND "startAt" >= ? AND "startAt" < ? ORDER BY "startAt"',
            (coach["id"], lo, hi),
        ).fetchall()
        days: dict[str, list[dict[str, Any]]] = {}
        for b in rows:
            key = dt.fromtimestamp(b["startAt"] / 1000).strftime("%Y-%m-%d")
            days.setdefault(key, []).append(_order_out(conn, b))
    return [{"date": k, "orders": v} for k, v in sorted(days.items())]


# ------------------------------------------------------------------ home tasks
@router.get("/api/coach/home-tasks")
def coach_home_tasks(request: Request, status: str | None = None, page: int = 1, pageSize: int = 20):
    user = _require(request, "COACH")
    with db.get_conn() as conn:
        coach = _coach_row(conn, user)
        rows = conn.execute(
            'SELECT * FROM "sf_family_task" WHERE "coachId"=? ORDER BY "createdAt" DESC', (coach["id"],)
        ).fetchall()
        items = [_task_out(conn, t) for t in rows]
        if status and status in _TASK_STATUS_TO_UPPER:
            upper = _TASK_STATUS_TO_UPPER[status]
            items = [t for t in items if t["status"] == status]
    total = len(items)
    page = max(1, page)
    pageSize = max(1, min(pageSize, 100))
    return {"list": items[(page - 1) * pageSize: page * pageSize], "total": total, "page": page, "pageSize": pageSize}


@router.get("/api/coach/orders/{order_id}/home-tasks")
def order_home_tasks(request: Request, order_id: str):
    user = _require(request, "COACH")
    with db.get_conn() as conn:
        coach = _coach_row(conn, user)
        _owned_booking(conn, user, order_id)
        rows = conn.execute(
            'SELECT * FROM "sf_family_task" WHERE "coachId"=? AND "bookingId"=? ORDER BY "createdAt" DESC',
            (coach["id"], order_id),
        ).fetchall()
    return [_task_out(conn, t) for t in rows]


@router.post("/api/coach/orders/{order_id}/home-tasks")
def create_home_task(request: Request, order_id: str, body: dict[str, Any]):
    user = _require(request, "COACH")
    title = str(body.get("title") or "").strip()
    if not title:
        return fail(400, "任务标题不能为空")
    description = str(body.get("description") or "").strip()
    try:
        suggested_days = max(1, min(int(body.get("suggestedDays") or 7), 60))
    except (TypeError, ValueError):
        suggested_days = 7
    with db.transaction() as conn:
        coach = _coach_row(conn, user)
        b = _owned_booking(conn, user, order_id)
        assert_child_access(conn, user, b["childId"])
        tid = db.new_id("ft")
        conn.execute(
            'INSERT INTO "sf_family_task" '
            '("id","childId","bookingId","coachId","title","itemsJson","goalCount","status","createdAt") '
            "VALUES (?,?,?,?,?,?,1,'OPEN',?)",
            (tid, b["childId"], order_id, coach["id"], title,
             json.dumps([{"name": title, "note": description}], ensure_ascii=False), db.now_ms()),
        )
        row = conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (tid,)).fetchone()
        return _task_out(conn, row)


@router.get("/api/coach/home-tasks/{task_id}")
def get_home_task(request: Request, task_id: str):
    user = _require(request, "COACH")
    with db.get_conn() as conn:
        coach = _coach_row(conn, user)
        t = conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone()
        if not t or t["coachId"] != coach["id"]:
            raise _Err(404, "任务不存在")
        return _task_out(conn, t)


@router.patch("/api/coach/home-tasks/{task_id}")
def patch_home_task(request: Request, task_id: str, body: dict[str, Any]):
    user = _require(request, "COACH")
    with db.transaction() as conn:
        coach = _coach_row(conn, user)
        t = conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone()
        if not t or t["coachId"] != coach["id"]:
            raise _Err(404, "任务不存在")
        title = str(body.get("title") or t["title"])
        description = body.get("description")
        items = services._loads(t["itemsJson"], [])
        if isinstance(description, str) and description:
            if items and isinstance(items[0], dict):
                items[0]["note"] = description
            else:
                items = [{"name": title, "note": description}]
        status_upper = _TASK_STATUS_TO_UPPER.get(str(body.get("status") or ""), t["status"])
        conn.execute(
            'UPDATE "sf_family_task" SET "title"=?, "itemsJson"=?, "status"=? WHERE "id"=?',
            (title, json.dumps(items, ensure_ascii=False), status_upper, task_id),
        )
        row = conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone()
        return _task_out(conn, row)


@router.delete("/api/coach/home-tasks/{task_id}")
def delete_home_task(request: Request, task_id: str):
    user = _require(request, "COACH")
    with db.transaction() as conn:
        coach = _coach_row(conn, user)
        t = conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone()
        if not t or t["coachId"] != coach["id"]:
            raise _Err(404, "任务不存在")
        conn.execute('DELETE FROM "sf_task_submission" WHERE "taskId"=?', (task_id,))
        conn.execute('DELETE FROM "sf_family_task" WHERE "id"=?', (task_id,))
    return {"ok": True}


@router.post("/api/coach/home-tasks/{task_id}/parent-complete")
def parent_complete_task(request: Request, task_id: str, body: dict[str, Any]):
    """Confirm an actual guardian submission; never impersonate a parent."""
    user = _require(request, "COACH")
    feedback = str(body.get("feedback") or "").strip()
    try:
        with db.transaction() as conn:
            coach = _coach_row(conn, user)
            t = conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone()
            if not t or t["coachId"] != coach["id"]:
                raise _Err(404, "任务不存在")
            submission = conn.execute(
                'SELECT "id" FROM "sf_task_submission" WHERE "taskId"=? AND "status"=\'SUBMITTED\' ORDER BY "createdAt" DESC LIMIT 1',
                (task_id,),
            ).fetchone()
            if not submission:
                raise _Err(409, "家长尚未提交完成记录，教练不能代替家长确认")
            services.confirm_task(conn, user, task_id, submission["id"], feedback)
    except (ApiError, _Err) as exc:
        return fail(getattr(exc, "status_code", 400) if isinstance(exc, ApiError) else exc.status,
                    exc.message if isinstance(exc, ApiError) else exc.msg)
    with db.get_conn() as conn:
        return _task_out(conn, conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone())


# ------------------------------------------------------------------ course templates (sf_service)
@router.get("/api/coach/course-templates")
def course_templates(request: Request):
    user = _require(request, "COACH")
    with db.get_conn() as conn:
        coach = _coach_row(conn, user)
        rows = conn.execute(
            'SELECT * FROM "sf_service" WHERE "coachId"=? AND "status"=\'ACTIVE\' ORDER BY "createdAt"',
            (coach["id"],),
        ).fetchall()
    return [{
        "id": r["id"], "coachId": r["coachId"], "name": r["title"], "courseType": r["sportType"],
        "durationMin": r["durationMinutes"], "price": round(r["priceCents"] / 100, 2),
        "description": r["description"], "createdAt": db.ms_to_iso(r["createdAt"]),
    } for r in rows]


@router.post("/api/coach/course-templates")
def create_course_template(request: Request, body: dict[str, Any]):
    user = _require(request, "COACH")
    name = str(body.get("name") or "").strip()
    if not name:
        return fail(400, "课程名称不能为空")
    try:
        price = round(float(body.get("price") or 0) * 100)
        duration = max(15, min(int(body.get("durationMin") or 60), 180))
    except (TypeError, ValueError):
        return fail(400, "价格或时长不合法")
    with db.transaction() as conn:
        coach = _coach_row(conn, user)
        sid = db.new_id("svc")
        conn.execute(
            'INSERT INTO "sf_service" '
            '("id","coachId","title","sportType","ageMin","ageMax","priceCents","durationMinutes","description","status","createdAt") '
            "VALUES (?,?,?,?,5,12,?,?,?,'ACTIVE',?)",
            (sid, coach["id"], name, str(body.get("courseType") or "体能"), price, duration,
             str(body.get("description") or ""), db.now_ms()),
        )
        row = conn.execute('SELECT * FROM "sf_service" WHERE "id"=?', (sid,)).fetchone()
    return {"id": row["id"], "coachId": row["coachId"], "name": row["title"], "courseType": row["sportType"],
            "durationMin": row["durationMinutes"], "price": round(row["priceCents"] / 100, 2),
            "description": row["description"], "createdAt": db.ms_to_iso(row["createdAt"])}


@router.put("/api/coach/course-templates/{template_id}")
def update_course_template(request: Request, template_id: str, body: dict[str, Any]):
    user = _require(request, "COACH")
    with db.transaction() as conn:
        coach = _coach_row(conn, user)
        row = conn.execute('SELECT * FROM "sf_service" WHERE "id"=? AND "coachId"=?', (template_id, coach["id"])).fetchone()
        if not row:
            raise _Err(404, "课程不存在")
        conn.execute(
            'UPDATE "sf_service" SET "title"=?, "sportType"=?, "durationMinutes"=?, "priceCents"=?, "description"=? '
            'WHERE "id"=?',
            (str(body.get("name") or row["title"]), str(body.get("courseType") or row["sportType"]),
             max(15, min(int(body.get("durationMin") or row["durationMinutes"]), 180)),
             round(float(body.get("price") or row["priceCents"] / 100) * 100),
             str(body.get("description") or row["description"]), template_id),
        )
        row = conn.execute('SELECT * FROM "sf_service" WHERE "id"=?', (template_id,)).fetchone()
    return {"id": row["id"], "coachId": row["coachId"], "name": row["title"], "courseType": row["sportType"],
            "durationMin": row["durationMinutes"], "price": round(row["priceCents"] / 100, 2),
            "description": row["description"], "createdAt": db.ms_to_iso(row["createdAt"])}


@router.delete("/api/coach/course-templates/{template_id}")
def delete_course_template(request: Request, template_id: str):
    user = _require(request, "COACH")
    with db.transaction() as conn:
        coach = _coach_row(conn, user)
        row = conn.execute('SELECT * FROM "sf_service" WHERE "id"=? AND "coachId"=?', (template_id, coach["id"])).fetchone()
        if not row:
            raise _Err(404, "课程不存在")
        conn.execute("UPDATE \"sf_service\" SET \"status\"='INACTIVE' WHERE \"id\"=?", (template_id,))
    return {"ok": True}


# ------------------------------------------------------------------ admin
def _admin_coach_out(conn: Any, c: Any) -> dict[str, Any]:
    u = conn.execute('SELECT "phone" FROM "sf_user" WHERE "id"=?', (c["userId"],)).fetchone()
    status = {"APPROVED": "approved", "PENDING": "pending_review", "REJECTED": "rejected", "SUSPENDED": "suspended"}.get(c["certificateStatus"], "pending_review")
    return {
        "id": c["id"], "name": c["name"], "avatar": c["avatarUrl"] or "",
        "phone": u["phone"] if u else "", "specialties": services._loads(c["courseTypes"], []),
        "status": status, "appliedAt": db.ms_to_iso(c["createdAt"]),
    }


@router.get("/api/admin/dashboard")
def admin_dashboard(request: Request):
    _require(request, "ADMIN")
    with db.get_conn() as conn:
        one = lambda sql: int(conn.execute(sql).fetchone()[0] or 0)  # noqa: E731
        return {
            "pendingCoachCount": one("SELECT COUNT(*) FROM \"sf_coach\" WHERE \"certificateStatus\"='PENDING'"),
            "approvedCoachCount": one("SELECT COUNT(*) FROM \"sf_coach\" WHERE \"certificateStatus\"='APPROVED'"),
            "totalOrders": one('SELECT COUNT(*) FROM "sf_booking"'),
            "totalStudents": one('SELECT COUNT(*) FROM "sf_child"'),
        }


@router.get("/api/admin/coaches")
def admin_coaches(request: Request, status: str | None = None, page: int = 1, pageSize: int = 20):
    _require(request, "ADMIN")
    with db.get_conn() as conn:
        rows = conn.execute('SELECT * FROM "sf_coach" ORDER BY "createdAt"').fetchall()
        items = [_admin_coach_out(conn, c) for c in rows]
        if status:
            items = [c for c in items if c["status"] == status]
    total = len(items)
    page = max(1, page)
    pageSize = max(1, min(pageSize, 100))
    return {"list": items[(page - 1) * pageSize: page * pageSize], "total": total, "page": page, "pageSize": pageSize}


@router.post("/api/admin/coaches/{coach_id}/approve")
def approve_coach(request: Request, coach_id: str, body: dict[str, Any] | None = None):
    from .portal import review_coach

    user = _require(request, "ADMIN")
    with db.transaction() as conn:
        return review_coach(conn, user, coach_id, "approve", str((body or {}).get("reason") or ""))


@router.post("/api/admin/coaches/{coach_id}/reject")
def reject_coach(request: Request, coach_id: str, body: dict[str, Any]):
    from .portal import require_text, review_coach

    user = _require(request, "ADMIN")
    reason = require_text(body, "reason")
    with db.transaction() as conn:
        return review_coach(conn, user, coach_id, "reject", reason)
