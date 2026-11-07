"""SportLink Motion Coach (MVP 1.1) regression tests.

Covers the ten required areas: auth/RBAC on the new endpoints, motion exercise
knowledge, session creation, pose feedback event validation (low confidence /
unknown error codes / dedup / pose-lost degradation), backend-verified
completion, star awarding, complete-idempotency, Motion Coach chat context,
and the Bailian-failure fallback. Runs fully offline on the mock LLM; the
degradation test injects a failing real-mode LLM stub.
"""
from __future__ import annotations

import pytest

from backend.llm import LLMError

DEMO_PASSWORD = "demo123456"
PARENT_PHONE = "13800000001"
OTHER_PARENT_PHONE = "13800000002"
COACH_PHONE = "13900000001"
OTHER_COACH_PHONE = "13900000002"
ADMIN_PHONE = "13700000000"


def login(client, phone: str, password: str = DEMO_PASSWORD) -> str:
    r = client.post("/api/auth/login", json={"phone": phone, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _reset_starfit():
    from backend.starfit.schema import ensure_schema
    from backend.starfit.seed import reset_demo_data

    ensure_schema()
    reset_demo_data()
    yield


def reps(client, token: str, session_id: str, count: int, confidence: float = 0.9):
    events = [{"type": "REP", "confidence": confidence, "clientMs": i * 1500} for i in range(count)]
    return client.post(f"/api/training/sessions/{session_id}/feedback", headers=h(token), json={"events": events})


def new_session(client, token: str, exercise_id: str = "ex_str_01", child: str = "c_xingxing", **extra) -> dict:
    r = client.post(
        "/api/training/sessions", headers=h(token),
        json={"childId": child, "exerciseId": exercise_id, **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


# ------------------------------------------------------------------ 1. auth & roles
def test_motion_endpoints_require_auth(client):
    assert client.get("/api/training/exercises").status_code == 401
    assert client.get("/api/training/sessions?childId=c_xingxing").status_code == 401
    assert client.post(
        "/api/training/sessions", json={"childId": "c_xingxing", "exerciseId": "ex_str_01"}
    ).status_code == 401
    assert client.post(
        "/api/agent/motion-coach/chat", json={"message": "开始"}
    ).status_code == 401


def test_motion_child_data_isolation(client):
    p1 = login(client, PARENT_PHONE)
    p2 = login(client, OTHER_PARENT_PHONE)
    admin = login(client, ADMIN_PHONE)

    assert client.post(
        "/api/training/sessions", headers=h(p2),
        json={"childId": "c_xingxing", "exerciseId": "ex_str_01"},
    ).status_code == 403
    session = new_session(client, p1)
    assert client.get(f"/api/training/sessions/{session['id']}", headers=h(p2)).status_code in (403, 404)
    assert client.get(f"/api/training/sessions/{session['id']}", headers=h(admin)).status_code == 200

    # coach with a real completed course may view; unrelated coach may not
    other = new_session(client, p1, exercise_id="ex_bal_01")
    coach = login(client, COACH_PHONE)
    other_coach = login(client, OTHER_COACH_PHONE)
    assert client.get(f"/api/training/sessions/{other['id']}", headers=h(other_coach)).status_code == 403
    # give coach_wang a real relationship via the booking chain
    client.post("/api/bookings", headers=h(p1), json={
        "childId": "c_xingxing", "serviceId": "svc_basketball",
        "startAt": "2026-11-14T09:00:00+08:00", "endAt": "2026-11-14T10:00:00+08:00",
    })
    bid = client.get("/api/bookings", headers=h(p1)).json()["data"]["items"][0]["id"]
    assert client.post(f"/api/bookings/{bid}/accept", headers=h(coach), json={}).status_code == 200
    assert client.get(f"/api/training/sessions/{other['id']}", headers=h(coach)).status_code == 200


# ------------------------------------------------------------------ 2. knowledge base
def test_motion_exercise_knowledge_base(client):
    p1 = login(client, PARENT_PHONE)
    r = client.get("/api/training/exercises", headers=h(p1))
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert r.json()["data"]["total"] == 3
    ids = {e["exerciseId"] for e in items}
    assert ids == {"ex_str_01", "ex_coo_01", "ex_bal_01"}
    squat = next(e for e in items if e["exerciseId"] == "ex_str_01")
    assert squat["motionConfig"]["kind"] == "REPS"
    assert squat["motionConfig"]["completion"] == {"type": "REPS", "reps": 8}
    assert squat["motionConfig"]["note"], "阈值必须有非医学声明"

    detail = client.get("/api/training/exercises/ex_bal_01", headers=h(p1)).json()["data"]
    assert detail["motionConfig"]["kind"] == "HOLD"
    assert detail["safetyNotes"], "知识库安全提示必须带出"

    disabled = client.get("/api/training/exercises/ex_str_02", headers=h(p1))
    assert disabled.status_code == 400
    assert disabled.json()["error"]["code"] == "NOT_MOTION_ENABLED"


# ------------------------------------------------------------------ 3. session creation
def test_training_session_creation_and_validation(client):
    p1 = login(client, PARENT_PHONE)
    session = new_session(client, p1, targetReps=4)
    assert session["status"] == "ACTIVE"
    assert session["mode"] == "POSE"
    assert session["counters"]["targetReps"] == 4
    assert session["exerciseName"] == "自重深蹲"

    assert client.post(
        "/api/training/sessions", headers=h(p1),
        json={"childId": "c_xingxing", "exerciseId": "ex_ghost"},
    ).status_code == 404
    # task belongs to another child
    assert client.post(
        "/api/training/sessions", headers=h(p1),
        json={"childId": "c_xingxing", "exerciseId": "ex_str_01", "taskId": "ft_demo_xiaoyue"},
    ).json()["error"]["code"] == "TASK_CHILD_MISMATCH"
    # valid task link
    ok = client.post(
        "/api/training/sessions", headers=h(p1),
        json={"childId": "c_xingxing", "exerciseId": "ex_coo_01", "taskId": "ft_demo_xingxing"},
    )
    assert ok.status_code == 201
    assert ok.json()["data"]["taskId"] == "ft_demo_xingxing"


# ------------------------------------------------------------------ 4. feedback events
def test_feedback_events_validate_and_persist(client):
    p1 = login(client, PARENT_PHONE)
    session = new_session(client, p1)
    sid = session["id"]

    r = reps(client, p1, sid, 3)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["counters"]["validRepCount"] == 3
    assert data["accepted"] == 3 and data["rejected"] == []
    assert data["progressRatio"] == pytest.approx(3 / 8)

    # low-confidence reps never count
    r = reps(client, p1, sid, 2, confidence=0.3)
    assert r.json()["data"]["counters"]["validRepCount"] == 3
    assert r.json()["data"]["rejected"][0]["reason"] == "LOW_CONFIDENCE"

    # unknown error code rejected
    bad = client.post(f"/api/training/sessions/{sid}/feedback", headers=h(p1), json={
        "events": [{"type": "FORM_ERROR", "code": "MADE_UP_CODE", "confidence": 0.9}],
    })
    assert bad.json()["data"]["rejected"][0]["reason"] == "ERROR_CODE_UNKNOWN"

    # duplicate form error within 2s window suppressed
    dup = client.post(f"/api/training/sessions/{sid}/feedback", headers=h(p1), json={
        "events": [
            {"type": "FORM_ERROR", "code": "TRUNK_LEAN", "confidence": 0.9},
            {"type": "FORM_ERROR", "code": "TRUNK_LEAN", "confidence": 0.9},
        ],
    })
    dup_data = dup.json()["data"]
    assert dup_data["counters"]["errorCounts"]["TRUNK_LEAN"] == 1
    assert dup_data["rejected"][0]["reason"] == "DUPLICATE_SUPPRESSED"

    # events persisted and visible in session detail
    detail = client.get(f"/api/training/sessions/{sid}", headers=h(p1)).json()["data"]
    assert detail["recentEvents"], "已接受的事件必须可查询"
    assert detail["counters"]["errorCounts"]["TRUNK_LEAN"] == 1


def test_feedback_rejected_after_completion(client):
    p1 = login(client, PARENT_PHONE)
    sid = new_session(client, p1, exercise_id="ex_bal_01")["id"]
    assert client.post(
        f"/api/training/sessions/{sid}/feedback", headers=h(p1),
        json={"events": [{"type": "HOLD", "holdMs": 21000, "confidence": 0.9}]},
    ).status_code == 200
    assert client.post(f"/api/training/sessions/{sid}/complete", headers=h(p1), json={}).status_code == 200
    late = client.post(
        f"/api/training/sessions/{sid}/feedback", headers=h(p1),
        json={"events": [{"type": "REP", "confidence": 0.9}]},
    )
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "TRAINING_SESSION_NOT_ACTIVE"


# ------------------------------------------------------------------ 5. pose-lost degradation
def test_pose_lost_does_not_count_and_blocks_completion(client):
    p1 = login(client, PARENT_PHONE)
    sid = new_session(client, p1)["id"]
    r = client.post(f"/api/training/sessions/{sid}/feedback", headers=h(p1), json={
        "events": [
            {"type": "POSE_LOST", "confidence": 0.2, "metrics": {"reason": "occlusion"}},
            {"type": "BOGUS"},
        ],
    })
    data = r.json()["data"]
    assert data["counters"]["poseLostCount"] == 1
    assert data["counters"]["validRepCount"] == 0
    assert data["rejected"][0]["reason"] == "EVENT_TYPE_UNKNOWN"

    done = client.post(f"/api/training/sessions/{sid}/complete", headers=h(p1), json={})
    assert done.status_code == 422
    body = done.json()["error"]
    assert body["code"] == "TRAINING_REQUIREMENTS_NOT_MET"
    assert "8" in body["message"]


# ------------------------------------------------------------------ 6+7+8. completion, stars, idempotency
def test_hold_completion_awards_star_idempotently(client):
    p1 = login(client, PARENT_PHONE)
    sid = new_session(client, p1, exercise_id="ex_bal_01")["id"]

    too_short = client.post(
        f"/api/training/sessions/{sid}/feedback", headers=h(p1),
        json={"events": [{"type": "HOLD", "holdMs": 12000, "confidence": 0.9}]},
    )
    assert too_short.json()["data"]["completionCheck"]["met"] is False

    assert client.post(
        f"/api/training/sessions/{sid}/feedback", headers=h(p1),
        json={"events": [{"type": "HOLD", "holdMs": 9000, "confidence": 0.9}]},
    ).status_code == 200

    done = client.post(f"/api/training/sessions/{sid}/complete", headers=h(p1), json={})
    assert done.status_code == 200
    data = done.json()["data"]
    assert data["idempotent"] is False
    assert data["result"]["completed"] is True
    assert data["result"]["holdSeconds"] == pytest.approx(21.0)
    assert [s["starType"] for s in data["starsAwarded"]] == ["HOME_TRAINING"]

    stars = client.get("/api/children/c_xingxing/stars", headers=h(p1)).json()["data"]
    assert stars["total"] == 1
    assert any(s["starType"] == "HOME_TRAINING" for s in stars["stars"])

    repeat = client.post(f"/api/training/sessions/{sid}/complete", headers=h(p1), json={})
    assert repeat.status_code == 200
    assert repeat.json()["data"]["idempotent"] is True
    stars_after = client.get("/api/children/c_xingxing/stars", headers=h(p1)).json()["data"]
    assert stars_after["total"] == 1, "重复完成绝不能二次发星"


def test_rep_completion_flow_with_session_list(client):
    p1 = login(client, PARENT_PHONE)
    sid = new_session(client, p1, targetReps=4)["id"]
    assert reps(client, p1, sid, 4).status_code == 200
    done = client.post(f"/api/training/sessions/{sid}/complete", headers=h(p1), json={})
    assert done.status_code == 200
    assert done.json()["data"]["result"]["completed"] is True

    listed = client.get("/api/training/sessions?childId=c_xingxing", headers=h(p1)).json()["data"]
    assert listed["total"] == 1
    assert listed["items"][0]["status"] == "COMPLETED"
    assert listed["items"][0]["result"]["id"] == done.json()["data"]["result"]["id"]


# ------------------------------------------------------------------ 9. Motion Coach chat context
def test_motion_coach_guidance_flow_and_context(client):
    p1 = login(client, PARENT_PHONE)
    first = client.post("/api/agent/motion-coach/chat", headers=h(p1), json={"message": "开始训练"}).json()["data"]
    assert first["agentKind"] == "MOTION"
    assert first["deterministic"] is True
    assert first["guidance"]["step"] == "DO"
    assert "自重深蹲" in first["guidance"]["text"], "默认应读取教练布置的家庭任务"
    sid = first["sessionId"]

    second = client.post(
        "/api/agent/motion-coach/chat", headers=h(p1),
        json={"message": "做完了", "sessionId": sid},
    ).json()["data"]
    assert second["sessionId"] == sid, "上下文必须延续"
    assert second["guidance"]["step"] == "REST", "做完后进入组间休息提醒"

    third = client.post(
        "/api/agent/motion-coach/chat", headers=h(p1),
        json={"message": "继续", "sessionId": sid},
    ).json()["data"]
    assert third["guidance"]["step"] == "DO"
    assert third["guidance"]["stepIndex"] == 1
    assert "开合跳" in third["guidance"]["text"]

    # motion sessions never bleed into the booking agent namespace
    booking = client.post("/api/agent/chat", headers=h(p1), json={"message": "你好"}).json()["data"]
    assert booking["sessionId"] != sid
    assert client.get(f"/api/agent/sessions/{sid}", headers=h(p1)).json()["data"]["state"]["motion"]["taskStep"] == 1


def test_motion_coach_summary_uses_real_results(client):
    p1 = login(client, PARENT_PHONE)
    sid = new_session(client, p1, exercise_id="ex_bal_01")["id"]
    client.post(
        f"/api/training/sessions/{sid}/feedback", headers=h(p1),
        json={"events": [{"type": "HOLD", "holdMs": 21000, "confidence": 0.9}]},
    )
    client.post(f"/api/training/sessions/{sid}/complete", headers=h(p1), json={})

    summary = client.post(
        "/api/agent/motion-coach/chat", headers=h(p1),
        json={"message": "总结一下今天的训练", "trainingSessionId": sid},
    ).json()["data"]
    assert "陪练星" in summary["reply"], "总结必须基于真实完成记录"


# ------------------------------------------------------------------ 10. Bailian failure fallback
def test_motion_coach_survives_llm_outage(client, monkeypatch):
    from backend.starfit import coach as sf_coach

    class ExplodingLLM:
        mode = "real"
        primary_model = "test-model"
        fc_supported = False

        def chat(self, *args, **kwargs):
            raise LLMError("模拟百炼不可达")

    p1 = login(client, PARENT_PHONE)
    result = sf_coach.run_motion_chat(
        ExplodingLLM(),  # type: ignore[arg-type]
        {"message": "总结一下今天的训练", "childId": "c_xingxing"},
        {"id": "u_parent_demo", "name": "林女士", "role": "PARENT"},
    )
    assert result["degraded"] is True
    assert result["deterministic"] is False
    assert result["reply"], "降级时也必须有可用的回复"
    # guidance for control words still works without any model
    ok = sf_coach.run_motion_chat(
        ExplodingLLM(),  # type: ignore[arg-type]
        {"message": "继续", "childId": "c_xingxing"},
        {"id": "u_parent_demo", "name": "林女士", "role": "PARENT"},
    )
    assert ok["deterministic"] is True
    assert ok["degraded"] is False
    assert "自重深蹲" in ok["reply"] or "单脚站立" in ok["reply"] or "开合跳" in ok["reply"]
