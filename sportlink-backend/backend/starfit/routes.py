"""StarFit HTTP API.

Mounted on the existing FastAPI app via app.include_router(router). All
responses use the same envelope contract as the legacy service:
{success, data, error, requestId} plus the x-request-id header. Errors raise
backend.agent.ApiError, already handled by create_app().
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from .. import db
from ..agent import ApiError
from ..llm import BailianClient
from ..models import StrictModel
from ..config import settings
from . import agent as sf_agent
from . import coach as sf_coach
from . import services
from .auth import (
    TOKEN_TTL_SECONDS,
    get_current_user,
    make_token,
    require_roles,
    verify_password,
)

router = APIRouter()


def ok(request: Request, data: Any, status_code: int = 200) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    response = JSONResponse(
        status_code=status_code,
        content={"success": True, "data": data, "error": None, "requestId": request_id},
    )
    response.headers["x-request-id"] = request_id
    return response


# ------------------------------------------------------------------ request bodies
class LoginBody(StrictModel):
    phone: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=1, max_length=128)


class ChildBody(StrictModel):
    nickname: str = Field(min_length=1, max_length=30)
    age: int = Field(ge=3, le=17)
    sportsInterests: list[str] = Field(default_factory=list)
    trainingGoals: list[str] = Field(default_factory=list)


class BookingBody(StrictModel):
    childId: str = Field(min_length=1)
    serviceId: str = Field(min_length=1)
    startAt: str = Field(min_length=1)
    endAt: str = Field(min_length=1)
    note: str | None = Field(default=None, max_length=500)
    address: str | None = Field(default=None, max_length=500)


class TrainingRecordBody(StrictModel):
    bookingId: str = Field(min_length=1)
    content: str = Field(min_length=1, max_length=2000)
    durationMinutes: int = Field(ge=1, le=240)
    performance: dict[str, Any] = Field(default_factory=dict)


class TaskBody(StrictModel):
    childId: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=100)
    items: list[Any] = Field(min_length=1)
    goalCount: int = 0
    bookingId: str | None = None


class SubmissionBody(StrictModel):
    content: str = Field(default="", max_length=1000)
    photoUrls: list[str] = Field(default_factory=list)


class ConfirmBody(StrictModel):
    coachFeedback: str = Field(default="", max_length=1000)


class TransitionBody(StrictModel):
    note: str = Field(default="", max_length=500)


class AgentChatBody(StrictModel):
    message: str = Field(min_length=1, max_length=4000)
    sessionId: str | None = None
    childId: str | None = None
    confirmationId: str | None = None
    context: dict[str, Any] | None = None


class TrainingSessionBody(StrictModel):
    childId: str = Field(min_length=1)
    exerciseId: str = Field(min_length=1)
    taskId: str | None = Field(default=None, max_length=64)
    mode: str = Field(default="POSE", max_length=10)
    targetReps: int | None = Field(default=None, ge=1, le=100)
    targetSeconds: int | None = Field(default=None, ge=5, le=600)


class PoseFeedbackBody(StrictModel):
    events: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class MotionChatBody(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    childId: str | None = Field(default=None, max_length=64)
    taskId: str | None = Field(default=None, max_length=64)
    trainingSessionId: str | None = Field(default=None, max_length=64)
    sessionId: str | None = Field(default=None, max_length=64)


AnyUser = Depends(get_current_user)
ParentOnly = Depends(require_roles("PARENT"))
CoachOnly = Depends(require_roles("COACH"))
AdminOnly = Depends(require_roles("ADMIN"))


# ------------------------------------------------------------------ auth
@router.post("/api/auth/login", tags=["A. 认证"], summary="使用手机号与真实密码登录")
def login(body: LoginBody, request: Request):
    with db.get_conn() as conn:
        row = conn.execute('SELECT * FROM "sf_user" WHERE "phone"=?', (body.phone,)).fetchone()
    if not body.password or not row or not verify_password(body.password, row["passwordHash"]):
        raise ApiError(401, "INVALID_CREDENTIALS", "手机号或密码错误")
    if row["status"] != "ACTIVE":
        raise ApiError(403, "USER_INACTIVE", "账号已停用")
    token = make_token(row["id"], row["role"])
    return ok(
        request,
        {
            "token": token,
            "tokenType": "Bearer",
            "expiresInSeconds": TOKEN_TTL_SECONDS,
            "user": {"id": row["id"], "phone": row["phone"], "name": row["name"], "role": row["role"]},
        },
    )


@router.get("/api/auth/me", tags=["A. 认证"], summary="当前登录用户与角色")
def me(request: Request, user: dict[str, Any] = AnyUser):
    with db.get_conn() as conn:
        coach = conn.execute('SELECT "id","name" FROM "sf_coach" WHERE "userId"=?', (user["id"],)).fetchone()
        children = conn.execute(
            'SELECT COUNT(*) FROM "sf_child" WHERE "guardianId"=?', (user["id"],)
        ).fetchone()[0]
    return ok(
        request,
        {
            "user": user,
            "coachProfile": dict(coach) if coach else None,
            "childrenCount": int(children),
            "permissions": {
                "parent": ["children", "bookings", "tasks", "agent", "stars"],
                "coach": ["bookings.accept", "bookings.complete", "training-records", "tasks", "agent"],
                "admin": ["coach.review", "stats", "read-all"],
            }.get(user["role"].lower(), []),
        },
    )


# ------------------------------------------------------------------ children
@router.post("/api/children", tags=["B. 儿童档案"], summary="家长创建儿童档案", status_code=201)
def create_child(body: ChildBody, request: Request, user: dict[str, Any] = ParentOnly):
    with db.transaction() as conn:
        data = services.create_child(conn, user, body.model_dump())
    return ok(request, data, 201)


@router.get("/api/children", tags=["B. 儿童档案"], summary="按角色返回有权访问的儿童档案")
def list_children(
    request: Request,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: dict[str, Any] = AnyUser,
):
    with db.get_conn() as conn:
        items = services.list_children(conn, user)
    return ok(request, services.paginate(items, page, pageSize))


@router.get("/api/children/{child_id}", tags=["B. 儿童档案"], summary="儿童档案详情（含权限校验）")
def get_child(child_id: str, request: Request, user: dict[str, Any] = AnyUser):
    with db.get_conn() as conn:
        return ok(request, services.get_child(conn, user, child_id))


# ------------------------------------------------------------------ coaches / services
@router.get("/api/coaches", tags=["C. 教练与课程"], summary="筛选已审核教练")
def list_coaches(
    request: Request,
    sportType: str | None = None,
    area: str | None = None,
    availableOn: str | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: dict[str, Any] = AnyUser,
):
    with db.get_conn() as conn:
        return ok(request, services.list_coaches(conn, sportType, area, availableOn, page, pageSize))


@router.get("/api/coaches/{coach_id}", tags=["C. 教练与课程"], summary="教练详情与课程")
def get_coach(coach_id: str, request: Request, user: dict[str, Any] = AnyUser):
    with db.get_conn() as conn:
        return ok(request, services.get_coach(conn, coach_id))


@router.get("/api/coaches/{coach_id}/slots", tags=["C. 教练与课程"], summary="教练真实可预约档期")
def get_coach_slots(
    coach_id: str,
    request: Request,
    fromDate: str | None = None,
    toDate: str | None = None,
    user: dict[str, Any] = AnyUser,
):
    with db.get_conn() as conn:
        return ok(request, services.get_coach_slots(conn, coach_id, fromDate, toDate))


@router.get("/api/services", tags=["C. 教练与课程"], summary="课程列表")
def list_services(
    request: Request,
    sportType: str | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: dict[str, Any] = AnyUser,
):
    with db.get_conn() as conn:
        return ok(request, services.list_services(conn, sportType, page, pageSize))


# ------------------------------------------------------------------ bookings
@router.post("/api/bookings", tags=["D. 预约订单"], summary="家长创建预约（模拟支付）", status_code=201)
def create_booking(body: BookingBody, request: Request, user: dict[str, Any] = ParentOnly):
    with db.transaction() as conn:
        data = services.create_booking(conn, user, body.model_dump())
    return ok(request, data, 201)


@router.get("/api/bookings", tags=["D. 预约订单"], summary="订单列表（按角色隔离）")
def list_bookings(
    request: Request,
    status: str | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: dict[str, Any] = AnyUser,
):
    with db.get_conn() as conn:
        return ok(request, services.list_bookings(conn, user, status, page, pageSize))


@router.get("/api/bookings/{booking_id}", tags=["D. 预约订单"], summary="订单详情")
def get_booking(booking_id: str, request: Request, user: dict[str, Any] = AnyUser):
    with db.get_conn() as conn:
        return ok(request, services.get_booking(conn, user, booking_id))


@router.post("/api/bookings/{booking_id}/accept", tags=["D. 预约订单"], summary="教练接单 PENDING -> ACCEPTED")
def accept_booking(
    booking_id: str, request: Request, body: TransitionBody = TransitionBody(),
    user: dict[str, Any] = CoachOnly,
):
    with db.transaction() as conn:
        return ok(request, services.transition_booking(conn, user, booking_id, "ACCEPTED", body.model_dump()))


@router.post("/api/bookings/{booking_id}/start", tags=["D. 预约订单"], summary="教练开课 ACCEPTED -> IN_PROGRESS")
def start_booking(
    booking_id: str, request: Request, body: TransitionBody = TransitionBody(),
    user: dict[str, Any] = CoachOnly,
):
    with db.transaction() as conn:
        return ok(request, services.transition_booking(conn, user, booking_id, "IN_PROGRESS", body.model_dump()))


@router.post("/api/bookings/{booking_id}/complete", tags=["D. 预约订单"], summary="完成课程并自动发放成长星星")
def complete_booking(
    booking_id: str, request: Request, body: TransitionBody = TransitionBody(),
    user: dict[str, Any] = CoachOnly,
):
    with db.transaction() as conn:
        return ok(request, services.transition_booking(conn, user, booking_id, "COMPLETED", body.model_dump()))


@router.post("/api/bookings/{booking_id}/cancel", tags=["D. 预约订单"], summary="取消订单")
def cancel_booking(
    booking_id: str, request: Request, body: TransitionBody = TransitionBody(),
    user: dict[str, Any] = AnyUser,
):
    with db.transaction() as conn:
        return ok(request, services.transition_booking(conn, user, booking_id, "CANCELLED", body.model_dump()))


# ------------------------------------------------------------------ training records / stars
@router.post("/api/training-records", tags=["E. 训练与星图"], summary="教练提交真实训练记录", status_code=201)
def create_training_record(body: TrainingRecordBody, request: Request, user: dict[str, Any] = CoachOnly):
    with db.transaction() as conn:
        data = services.create_training_record(conn, user, body.model_dump())
    return ok(request, data, 201)


@router.get("/api/children/{child_id}/training-records", tags=["E. 训练与星图"], summary="儿童训练记录（含权限校验）")
def list_training_records(
    child_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: dict[str, Any] = AnyUser,
):
    with db.get_conn() as conn:
        return ok(request, services.list_training_records(conn, user, child_id, page, pageSize))


@router.get("/api/children/{child_id}/stars", tags=["E. 训练与星图"], summary="成长星图（前端可直接渲染）")
def get_stars(child_id: str, request: Request, user: dict[str, Any] = AnyUser):
    with db.get_conn() as conn:
        return ok(request, services.get_stars(conn, user, child_id))


@router.post("/api/growth-events/{event_id}/seen", tags=["E. 训练与星图"], summary="确认已查看成长星点亮事件")
def mark_growth_event_seen(event_id: str, request: Request, user: dict[str, Any] = ParentOnly):
    with db.transaction() as conn:
        services.mark_growth_event_seen(conn, user, event_id)
    return ok(request, {"seen": True})


# ------------------------------------------------------------------ exercise knowledge base / videos
@router.get("/api/exercises", tags=["F. 知识库与视频"], summary="运动动作知识库检索")
def list_exercises(
    request: Request,
    category: str | None = None,
    keyword: str | None = None,
    age: int | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: dict[str, Any] = AnyUser,
):
    with db.get_conn() as conn:
        return ok(request, services.list_exercises(conn, category, keyword, age, page, pageSize))


@router.get("/api/exercises/{exercise_id}", tags=["F. 知识库与视频"], summary="动作详情")
def get_exercise(exercise_id: str, request: Request, user: dict[str, Any] = AnyUser):
    with db.get_conn() as conn:
        return ok(request, services.get_exercise(conn, exercise_id))


@router.get("/api/videos", tags=["F. 知识库与视频"], summary="教学视频列表")
def list_videos(
    request: Request,
    category: str | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: dict[str, Any] = AnyUser,
):
    with db.get_conn() as conn:
        return ok(request, services.list_videos(conn, category, page, pageSize))


# ------------------------------------------------------------------ family tasks
@router.post("/api/tasks", tags=["G. 家庭任务"], summary="教练布置家庭训练任务", status_code=201)
def create_task(body: TaskBody, request: Request, user: dict[str, Any] = CoachOnly):
    with db.transaction() as conn:
        data = services.create_task(conn, user, body.model_dump())
    return ok(request, data, 201)


@router.get("/api/tasks", tags=["G. 家庭任务"], summary="家庭任务列表")
def list_tasks(
    request: Request,
    childId: str | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: dict[str, Any] = AnyUser,
):
    with db.get_conn() as conn:
        return ok(request, services.list_tasks(conn, user, childId, page, pageSize))


@router.post("/api/tasks/{task_id}/submissions", tags=["G. 家庭任务"], summary="家长提交任务完成记录", status_code=201)
def submit_task(
    task_id: str, body: SubmissionBody, request: Request, user: dict[str, Any] = ParentOnly,
):
    with db.transaction() as conn:
        return ok(request, services.submit_task(conn, user, task_id, body.model_dump()), 201)


@router.get("/api/tasks/{task_id}/submissions", tags=["G. 家庭任务"], summary="任务提交记录")
def list_submissions(task_id: str, request: Request, user: dict[str, Any] = AnyUser):
    with db.get_conn() as conn:
        return ok(request, services.list_submissions(conn, user, task_id))


@router.post(
    "/api/tasks/{task_id}/submissions/{submission_id}/confirm",
    tags=["G. 家庭任务"], summary="教练确认任务完成并自动发放挑战星",
)
def confirm_task(
    task_id: str, submission_id: str, body: ConfirmBody, request: Request,
    user: dict[str, Any] = CoachOnly,
):
    with db.transaction() as conn:
        return ok(request, services.confirm_task(conn, user, task_id, submission_id, body.coachFeedback))


# ------------------------------------------------------------------ AI Agent
@router.post("/api/agent/chat", tags=["H. AI Agent"], summary="Function Calling 对话（工具真实调用后端）")
def agent_chat(body: AgentChatBody, request: Request, user: dict[str, Any] = AnyUser):
    llm: BailianClient = request.app.state.llm
    return ok(request, sf_agent.run_chat(llm, body.model_dump(), user))


@router.get("/api/agent/sessions/{session_id}", tags=["H. AI Agent"], summary="Agent 会话与工具调用轨迹")
def agent_session(session_id: str, request: Request, user: dict[str, Any] = AnyUser):
    with db.get_conn() as conn:
        return ok(request, sf_agent.get_session(conn, user, session_id))


# ------------------------------------------------------------------ motion coach (SportLink MVP 1.1)
@router.post(
    "/api/agent/motion-coach/chat", tags=["H. AI Agent"],
    summary="AI 运动陪练对话（模式 B 提醒/鼓励；独立提示词与只读工具权限）",
)
def motion_coach_chat(body: MotionChatBody, request: Request, user: dict[str, Any] = AnyUser):
    llm: BailianClient = request.app.state.llm
    return ok(request, sf_coach.run_motion_chat(llm, body.model_dump(), user))


@router.get("/api/training/exercises", tags=["J. 运动陪练"], summary="支持姿态识别训练的动作与规则配置")
def list_motion_exercises(request: Request, user: dict[str, Any] = AnyUser):
    with db.get_conn() as conn:
        items = services.list_motion_exercises(conn)
    return ok(request, {"total": len(items), "items": items})


@router.get("/api/training/exercises/{exercise_id}", tags=["J. 运动陪练"], summary="动作训练配置详情（阈值仅演示用）")
def get_motion_exercise(exercise_id: str, request: Request, user: dict[str, Any] = AnyUser):
    from . import pose as pose_engine

    with db.get_conn() as conn:
        detail = services.get_exercise(conn, exercise_id)
    config = pose_engine.MOTION_CONFIGS.get(exercise_id)
    if not config:
        raise ApiError(400, "NOT_MOTION_ENABLED", f"动作 {detail['name']} 暂不支持姿态识别训练")
    return ok(request, {**detail, "motionConfig": config})


@router.post("/api/training/sessions", tags=["J. 运动陪练"], summary="创建训练会话（家长/教练，含所属关系校验）", status_code=201)
def create_training_session(body: TrainingSessionBody, request: Request, user: dict[str, Any] = AnyUser):
    with db.transaction() as conn:
        data = services.create_training_session(conn, user, body.model_dump())
    return ok(request, data, 201)


@router.get("/api/training/sessions", tags=["J. 运动陪练"], summary="训练会话列表（按儿童，含完成结果）")
def list_training_sessions(
    childId: str, request: Request, page: int = 1, pageSize: int = 20,
    user: dict[str, Any] = AnyUser,
):
    with db.get_conn() as conn:
        return ok(request, services.list_training_sessions(conn, user, childId, page, pageSize))


@router.get("/api/training/sessions/{session_id}", tags=["J. 运动陪练"], summary="训练会话详情（计数、规则引擎判定、最近事件）")
def get_training_session(session_id: str, request: Request, user: dict[str, Any] = AnyUser):
    with db.get_conn() as conn:
        row = services._session_row(conn, user, session_id)
        data = services.training_session_out(conn, row)
        events = conn.execute(
            'SELECT "type","code","confidence","createdAt" FROM "sf_pose_feedback_event" '
            'WHERE "sessionId"=? ORDER BY "createdAt" DESC LIMIT 20',
            (session_id,),
        ).fetchall()
        data["recentEvents"] = [
            {"type": e["type"], "code": e["code"], "confidence": e["confidence"],
             "at": db.ms_to_iso(e["createdAt"])}
            for e in reversed(events)
        ]
    return ok(request, data)


@router.post("/api/training/sessions/{session_id}/feedback", tags=["J. 运动陪练"], summary="上报姿态规则引擎事件（仅结构化指标，不传视频）")
def add_pose_feedback(session_id: str, body: PoseFeedbackBody, request: Request, user: dict[str, Any] = AnyUser):
    with db.transaction() as conn:
        data = services.add_pose_feedback(conn, user, session_id, body.events)
    return ok(request, data)


@router.post("/api/training/sessions/{session_id}/complete", tags=["J. 运动陪练"], summary="结束训练（后端按规则校验达标，幂等发放陪练星）")
def complete_training_session(session_id: str, request: Request, user: dict[str, Any] = AnyUser):
    with db.transaction() as conn:
        data = services.complete_training_session(conn, user, session_id)
    return ok(request, data)


# ------------------------------------------------------------------ health / admin
@router.get("/api/starfit/health", tags=["I. 系统"], summary="StarFit 平台状态（公开）")
def starfit_health(request: Request):
    llm: BailianClient = request.app.state.llm
    with db.get_conn() as conn:
        counts = {
            "exercises": conn.execute('SELECT COUNT(*) FROM "sf_exercise"').fetchone()[0],
            "coaches": conn.execute('SELECT COUNT(*) FROM "sf_coach"').fetchone()[0],
            "children": conn.execute('SELECT COUNT(*) FROM "sf_child"').fetchone()[0],
            "bookings": conn.execute('SELECT COUNT(*) FROM "sf_booking"').fetchone()[0],
            "growthStars": conn.execute('SELECT COUNT(*) FROM "sf_growth_star"').fetchone()[0],
        }
    return ok(
        request,
        {
            "status": "ok",
            "service": "StarFit (星动到家) backend extension",
            "database": settings.DATABASE_PATH,
            "llmMode": llm.mode,
            "model": llm.primary_model,
            "fcSupported": llm.fc_supported,
            "apiKeyConfigured": bool(llm.config.api_key_present),
            "counts": counts,
            "legacyApiPreserved": ["/api/v1/health", "/api/v1/ai/chat", "/api/v1/agent-runs", "/api/v1/dashboard/summary"],
        },
    )


@router.get("/api/admin/stats", tags=["I. 系统"], summary="管理员订单与业务统计")
def admin_stats(request: Request, user: dict[str, Any] = AdminOnly):
    with db.get_conn() as conn:
        return ok(request, services.admin_stats(conn))


# ------------------------------------------------------------------ demo pages & spec aliases (MVP 1.2)
@router.get("/motion-coach", include_in_schema=False)
def motion_coach_page():
    from pathlib import Path

    page = Path(__file__).resolve().parent.parent / "static" / "motion" / "index.html"
    from fastapi.responses import FileResponse

    return FileResponse(page, media_type="text/html")


@router.get("/demo", include_in_schema=False)
def demo_console_page():
    from pathlib import Path

    page = Path(__file__).resolve().parent.parent / "static" / "demo" / "index.html"
    from fastapi.responses import FileResponse

    return FileResponse(page, media_type="text/html")


@router.get("/console", include_in_schema=False)
def coach_admin_console_page():
    from pathlib import Path

    page = Path(__file__).resolve().parent.parent / "static" / "console" / "index.html"
    from fastapi.responses import FileResponse

    return FileResponse(page, media_type="text/html")


@router.get("/coach-app", include_in_schema=False)
def coach_admin_react_app():
    """React 教练端/管理端（starfit-coach-admin 构建产物，HashRouter + 真实 API）。"""
    from pathlib import Path

    page = Path(__file__).resolve().parent.parent / "static" / "coachapp" / "index.html"
    from fastapi.responses import FileResponse

    return FileResponse(page, media_type="text/html")


@router.get("/api/courses", tags=["C. 教练与课程"], summary="课程列表（/api/services 的规格别名）")
def list_courses_alias(
    sportType: str | None = None, request: Request = None, page: int = 1, pageSize: int = 20,
    user: dict[str, Any] = AnyUser,
):
    with db.get_conn() as conn:
        return ok(request, services.list_services(conn, sportType, page, pageSize))


@router.get("/api/children/{child_id}/growth", tags=["E. 训练与星图"], summary="成长总览：星图 + 训练会话 + 教练反馈（真实记录）")
def child_growth(child_id: str, request: Request, user: dict[str, Any] = AnyUser):
    with db.get_conn() as conn:
        stars = services.get_stars(conn, user, child_id)
        sessions = services.list_training_sessions(conn, user, child_id, 1, 50)
        records = services.list_training_records(conn, user, child_id, 1, 20)
    return ok(request, {
        "childId": child_id,
        "starMap": stars,
        "trainingSessions": sessions["items"],
        "coachFeedback": records["items"],
        "totals": {
            "stars": stars["total"],
            "completedSessions": sum(1 for s in sessions["items"] if s["status"] == "COMPLETED"),
            "coachRecords": records["total"],
        },
    })
