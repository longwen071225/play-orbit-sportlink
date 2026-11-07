"""StarFit P0 regression tests.

Runs on the existing pytest harness (tests/conftest.py): isolated SQLite DB
built from the committed Prisma migration, offline mock LLM, real FastAPI app.
Covers: auth/RBAC, child-data isolation, booking state machine + conflict,
training completion -> star awarding + idempotency, Agent tool calling and the
confirmation gate, knowledge base, and preservation of legacy endpoints.
"""
from __future__ import annotations

import pytest

DEMO_PASSWORD = "demo123456"

PARENT_PHONE = "13800000001"
OTHER_PARENT_PHONE = "13800000002"
COACH_PHONE = "13900000001"
OTHER_COACH_PHONE = "13900000002"
ADMIN_PHONE = "13700000000"

BOOKING_BODY = {
    "childId": "c_xingxing",
    "serviceId": "svc_basketball",
    "startAt": "2026-11-14T09:00:00+08:00",
    "endAt": "2026-11-14T10:00:00+08:00",
}


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


def new_booking(client, token: str, **overrides) -> dict:
    r = client.post("/api/bookings", headers=h(token), json={**BOOKING_BODY, **overrides})
    assert r.status_code == 201, r.text
    return r.json()["data"]


def completed_course(client, parent: str, coach: str) -> dict:
    """Real chain: create -> accept -> start -> training record -> complete."""
    booking = new_booking(client, parent)
    bid = booking["id"]
    assert client.post(f"/api/bookings/{bid}/accept", headers=h(coach), json={}).status_code == 200
    assert client.post(f"/api/bookings/{bid}/start", headers=h(coach), json={}).status_code == 200
    rec = client.post(
        "/api/training-records",
        headers=h(coach),
        json={
            "bookingId": bid,
            "content": "完成 20 分钟运球与平衡练习，单脚站立较上周更稳定",
            "durationMinutes": 20,
            "performance": {"balance": 4, "notes": "教练现场评价"},
        },
    )
    assert rec.status_code == 201, rec.text
    done = client.post(f"/api/bookings/{bid}/complete", headers=h(coach), json={})
    assert done.status_code == 200, done.text
    return {"booking": booking, "completion": done.json()["data"]}


# ------------------------------------------------------------------ auth / envelope
def test_login_me_and_auth_required(client):
    assert client.get("/api/children").status_code == 401
    bad = client.post("/api/auth/login", json={"phone": PARENT_PHONE, "password": "wrong"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "INVALID_CREDENTIALS"

    token = login(client, PARENT_PHONE)
    me = client.get("/api/auth/me", headers=h(token))
    assert me.status_code == 200
    body = me.json()
    assert body["success"] is True and body["error"] is None and body["requestId"]
    assert me.headers.get("x-request-id") == body["requestId"]
    assert body["data"]["user"]["role"] == "PARENT"
    assert body["data"]["childrenCount"] == 2


def test_parent_can_create_multiple_children(client):
    token = login(client, PARENT_PHONE)
    r = client.post(
        "/api/children", headers=h(token),
        json={"nickname": "小辰", "age": 7, "sportsInterests": ["跳绳"], "trainingGoals": ["协调性"]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["guardianId"] == "u_parent_demo"
    assert client.get("/api/children", headers=h(token)).json()["data"]["total"] == 3


# ------------------------------------------------------------------ child isolation
def test_child_data_isolation(client):
    p1 = login(client, PARENT_PHONE)
    p2 = login(client, OTHER_PARENT_PHONE)
    coach = login(client, COACH_PHONE)
    admin = login(client, ADMIN_PHONE)

    assert client.get("/api/children/c_xingxing", headers=h(p1)).status_code == 200
    assert client.get("/api/children/c_other", headers=h(p1)).status_code == 403
    assert client.get("/api/children/c_other", headers=h(p2)).status_code == 200
    assert client.get("/api/children/c_xingxing", headers=h(coach)).status_code == 403
    assert client.get("/api/children/c_xingxing", headers=h(admin)).status_code == 200

    ids = [c["id"] for c in client.get("/api/children", headers=h(p1)).json()["data"]["items"]]
    assert "c_other" not in ids

    forbidden = client.post("/api/bookings", headers=h(p2), json=BOOKING_BODY)
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "CHILD_ACCESS_DENIED"

    # A merely submitted (PENDING) booking grants the coach NO access; only an
    # accepted/in-progress/completed booking for their own profile does.
    b = new_booking(client, p1)
    assert client.get("/api/children/c_xingxing", headers=h(coach)).status_code == 403
    assert client.post(f"/api/bookings/{b['id']}/accept", headers=h(coach), json={}).status_code == 200
    assert client.get("/api/children/c_xingxing", headers=h(coach)).status_code == 200
    assert client.get("/api/children/c_xiaoyue", headers=h(coach)).status_code == 403


# ------------------------------------------------------------------ booking state machine
def test_booking_state_machine_and_conflict(client):
    parent = login(client, PARENT_PHONE)
    coach = login(client, COACH_PHONE)
    other_coach = login(client, OTHER_COACH_PHONE)

    b = new_booking(client, parent)
    assert b["status"] == "PENDING"
    assert b["paymentStatus"] == "SIMULATED_UNPAID"
    assert b["amountCents"] == 19900  # price from DB, not from request
    bid = b["id"]

    assert client.post(f"/api/bookings/{bid}/accept", headers=h(parent), json={}).status_code == 403
    assert client.post(f"/api/bookings/{bid}/accept", headers=h(other_coach), json={}).status_code == 403
    jump = client.post(f"/api/bookings/{bid}/complete", headers=h(coach), json={})
    assert jump.status_code == 409
    assert jump.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    dup = client.post("/api/bookings", headers=h(parent), json=BOOKING_BODY)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "BOOKING_CONFLICT"

    accepted = client.post(f"/api/bookings/{bid}/accept", headers=h(coach), json={}).json()["data"]["booking"]
    assert accepted["status"] == "ACCEPTED"
    assert accepted["paymentStatus"] == "SIMULATED_PAID"
    started = client.post(f"/api/bookings/{bid}/start", headers=h(coach), json={}).json()["data"]["booking"]
    assert started["status"] == "IN_PROGRESS"

    no_record = client.post(f"/api/bookings/{bid}/complete", headers=h(coach), json={})
    assert no_record.status_code == 409
    assert no_record.json()["error"]["code"] == "TRAINING_RECORD_REQUIRED"

    # A cancelled booking frees the slot again.
    cancel = client.post(f"/api/bookings/{bid}/cancel", headers=h(parent), json={})
    assert cancel.status_code == 200
    assert cancel.json()["data"]["booking"]["status"] == "CANCELLED"
    assert client.post("/api/bookings", headers=h(parent), json=BOOKING_BODY).status_code == 201


# ------------------------------------------------------------------ stars / idempotency
def test_training_completion_awards_stars_once(client):
    parent = login(client, PARENT_PHONE)
    coach = login(client, COACH_PHONE)
    result = completed_course(client, parent, coach)
    awarded = result["completion"]["starsAwarded"]
    assert len(awarded) >= 2
    assert {"FIRST_COURSE", "BASKETBALL"} <= {s["starType"] for s in awarded}

    stars = client.get("/api/children/c_xingxing/stars", headers=h(parent)).json()["data"]
    assert stars["total"] == len(awarded)
    assert all("position" in s["metadata"] for s in stars["stars"])
    assert stars["disclaimer"]

    # Terminal state cannot be completed again.
    bid = result["booking"]["id"]
    assert client.post(f"/api/bookings/{bid}/complete", headers=h(coach), json={}).status_code == 409

    # Direct duplicate award is a no-op (unique event + reward_event).
    from backend import db
    from backend.starfit import stars as star_rules

    with db.transaction() as conn:
        assert star_rules.award_star(conn, "c_xingxing", "FIRST_COURSE", "BOOKING", bid) is None
    after = client.get("/api/children/c_xingxing/stars", headers=h(parent)).json()["data"]
    assert after["total"] == stars["total"]


def test_parent_booking_is_shared_and_every_completed_course_adds_a_star(client):
    parent = login(client, PARENT_PHONE)
    wang = login(client, COACH_PHONE)
    zhang = login(client, "13900000003")
    admin = login(client, ADMIN_PHONE)
    completed_course(client, parent, wang)

    booking = new_booking(
        client, parent, serviceId="svc_fitness",
        startAt="2026-11-15T09:00:00+08:00", endAt="2026-11-15T02:00:00Z",
    )
    bid = booking["id"]
    coach_url = f"/api/portal/coach/orders/{bid}"
    admin_url = f"/api/portal/admin/orders/{bid}"
    stars_url = "/api/children/c_xingxing/stars"

    assigned = client.get(f"/api/portal/coach/orders?q={bid}", headers=h(zhang)).json()["list"]
    managed = client.get(f"/api/portal/admin/orders?q={bid}", headers=h(admin)).json()["list"]
    assert len(assigned) == 1 and assigned == managed
    assert assigned[0]["id"] == bid and assigned[0]["coachId"] == "coach_zhang"
    assert assigned[0]["status"] == "pending"
    assert assigned[0]["scheduledAt"] == booking["startAt"]
    assert client.get(f"/api/portal/coach/orders?q={bid}", headers=h(wang)).json()["list"] == []

    assert client.post(f"{coach_url}/accept", headers=h(zhang)).status_code == 200
    assert client.post(f"{coach_url}/start", headers=h(zhang)).status_code == 200
    feedback = {"content": "完成基础耐力训练", "durationMin": 40, "performance": "good"}
    assert client.post(f"{coach_url}/feedback", headers=h(zhang), json=feedback).status_code == 200
    before = client.get(stars_url, headers=h(parent)).json()["data"]
    assert all(s["sourceId"] != bid for s in before["stars"])

    completed = client.post(f"{coach_url}/complete", headers=h(zhang))
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert client.get(admin_url, headers=h(admin)).json()["status"] == "completed"
    assert client.get(f"/api/bookings/{bid}", headers=h(parent)).json()["data"]["status"] == "COMPLETED"
    assert client.post(f"{coach_url}/complete", headers=h(zhang)).status_code == 409
    assert client.post(f"{coach_url}/feedback", headers=h(zhang), json=feedback).status_code == 200

    after = client.get(stars_url, headers=h(parent)).json()["data"]
    assert after["total"] == before["total"] + 1
    star, = [s for s in after["stars"] if s["sourceId"] == bid]
    assert star["starType"] == "COURSE_COMPLETED"
    assert star["coachId"] == "coach_zhang" and star["durationMinutes"] == 40
    assert star["recordId"] == completed.json()["trainingLog"]["id"]
    event, = [event for event in after["events"] if event["nodeId"] == star["starId"]]
    assert event["recordId"] == star["recordId"]
    seen_url = f"/api/growth-events/{event['eventId']}/seen"
    assert client.post(seen_url, headers=h(login(client, OTHER_PARENT_PHONE))).status_code == 403
    assert client.post(seen_url, headers=h(parent)).status_code == 200
    assert client.post(seen_url, headers=h(parent)).status_code == 200
    refreshed = client.get(stars_url, headers=h(parent)).json()["data"]
    assert refreshed["stars"] == after["stars"]
    assert event not in refreshed["events"]


def test_family_task_awards_challenge_star_only_after_coach_confirmation(client):
    parent = login(client, PARENT_PHONE)
    coach = login(client, COACH_PHONE)
    completed_course(client, parent, coach)  # coach gains access + first stars

    task = client.post(
        "/api/tasks", headers=h(coach),
        json={"childId": "c_xingxing", "title": "平衡小勇士",
              "items": ["单脚站立", "敏捷梯", "跨越障碍物"], "goalCount": 3},
    )
    assert task.status_code == 201, task.text
    tid = task.json()["data"]["id"]

    sub = client.post(
        f"/api/tasks/{tid}/submissions", headers=h(parent),
        json={"content": "已完成 3 项家庭运动", "photoUrls": []},
    )
    assert sub.status_code == 201, sub.text
    assert sub.json()["data"]["starsAwarded"] == []  # no star before coach confirms
    sid = sub.json()["data"]["submission"]["id"]

    conf = client.post(
        f"/api/tasks/{tid}/submissions/{sid}/confirm", headers=h(coach),
        json={"coachFeedback": "动作完成质量不错"},
    )
    assert conf.status_code == 200
    awarded = conf.json()["data"]["starsAwarded"]
    assert len(awarded) == 1
    assert awarded[0]["starType"] == "HOME_CHALLENGE"

    again = client.post(
        f"/api/tasks/{tid}/submissions/{sid}/confirm", headers=h(coach),
        json={"coachFeedback": "重复确认"},
    )
    assert again.json()["data"]["starsAwarded"] == []  # idempotent

    stars = client.get("/api/children/c_xingxing/stars", headers=h(parent)).json()["data"]
    assert sum(1 for s in stars["stars"] if s["starType"] == "HOME_CHALLENGE") == 1


# ------------------------------------------------------------------ AI Agent
def test_agent_tool_calling_confirmation_gate_and_real_booking(client):
    parent = login(client, PARENT_PHONE)

    r = client.post(
        "/api/agent/chat", headers=h(parent),
        json={"message": "我家孩子8岁，协调性不太好，有没有适合他的运动？", "childId": "c_xingxing"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    names = {t["name"] for t in data["toolCalls"]}
    assert {"get_child_profile", "get_training_history", "search_exercises", "generate_training_plan"} <= names
    assert data["llmMode"] == "mock"
    assert all(t["status"] == "success" for t in data["toolCalls"])
    profile = next(t for t in data["toolCalls"] if t["name"] == "get_child_profile")
    assert profile["result"]["child"]["nickname"] == "小星"  # real DB row, not fabricated

    sess = client.get(f"/api/agent/sessions/{data['sessionId']}", headers=h(parent))
    assert sess.status_code == 200
    assert len(sess.json()["data"]["messages"]) > 0

    r2 = client.post(
        "/api/agent/chat", headers=h(parent),
        json={
            "message": "帮我找一个周末有空的篮球教练，并预约周六上午",
            "childId": "c_xingxing",
            "context": {
                "serviceId": "svc_basketball",
                "startAt": "2026-11-14T09:00:00+08:00",
                "endAt": "2026-11-14T10:00:00+08:00",
            },
        },
    )
    assert r2.status_code == 200, r2.text
    d2 = r2.json()["data"]
    assert d2["pendingConfirmation"] is not None
    assert d2["pendingConfirmation"]["action"] == "create_booking"
    assert client.get("/api/bookings", headers=h(parent)).json()["data"]["total"] == 0

    token = d2["pendingConfirmation"]["confirmationId"]
    r3 = client.post(
        "/api/agent/chat", headers=h(parent),
        json={"message": "确认预约", "sessionId": d2["sessionId"],
              "childId": "c_xingxing", "confirmationId": token},
    )
    assert r3.status_code == 200, r3.text
    created = [t for t in r3.json()["data"]["toolCalls"] if t["name"] == "create_booking"]
    assert created and created[0]["status"] == "success", created
    assert client.get("/api/bookings", headers=h(parent)).json()["data"]["total"] == 1


def test_agent_rejects_forged_confirmation_token(client):
    parent = login(client, PARENT_PHONE)
    from backend import db
    from backend.starfit.agent import ToolContext, execute_tool

    with db.transaction() as conn:
        ctx = ToolContext(
            conn=conn,
            user={"id": "u_parent_demo", "role": "PARENT", "phone": PARENT_PHONE, "name": "林女士"},
            session_id="s_forged", state={"pendingConfirmations": []},
            confirmation_id="cf_forged", context={},
        )
        result = execute_tool(
            "create_booking",
            {
                "child_id": "c_xingxing", "service_id": "svc_basketball",
                "start_at": "2026-11-14T09:00:00+08:00",
                "end_at": "2026-11-14T10:00:00+08:00",
                "confirmation_id": "cf_forged",
            },
            ctx,
        )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "INVALID_CONFIRMATION"
    assert client.get("/api/bookings", headers=h(parent)).json()["data"]["total"] == 0


def test_tool_whitelist_rejects_unknown_tool(client):
    from backend import db
    from backend.starfit.agent import ToolContext, execute_tool

    with db.transaction() as conn:
        ctx = ToolContext(
            conn=conn, user={"id": "u_parent_demo", "role": "PARENT"},
            session_id="s_whitelist", state={}, context={},
        )
        result = execute_tool("drop_all_tables", {}, ctx)
    assert result["error"]["code"] == "TOOL_NOT_WHITELISTED"


# ------------------------------------------------------------------ knowledge base / legacy
def test_exercise_knowledge_base_covers_eight_categories(client):
    token = login(client, PARENT_PHONE)
    data = client.get("/api/exercises?pageSize=100", headers=h(token)).json()["data"]
    assert data["total"] >= 30
    categories = {e["category"] for e in data["items"]}
    for c in ["平衡训练", "协调性训练", "敏捷训练", "基础力量",
              "基础耐力", "篮球基础", "跳跃训练", "亲子互动运动"]:
        assert c in categories
    assert all(e["videoUrl"] == "" and e["model3dUrl"] == "" for e in data["items"]), "演示数据不得编造资源链接"

    one = client.get("/api/exercises/ex_bal_01", headers=h(token)).json()["data"]
    assert one["name"] == "单脚站立"
    assert one["instructions"] and one["commonMistakes"] and one["safetyNotes"]
    assert client.get("/api/videos", headers=h(token)).json()["data"]["total"] >= 1


def test_legacy_solopilot_endpoints_still_work(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["success"] is True
    assert client.get("/api/v1/dashboard/summary").status_code == 200


def test_admin_stats_role_guard(client):
    parent = login(client, PARENT_PHONE)
    admin = login(client, ADMIN_PHONE)
    assert client.get("/api/admin/stats", headers=h(parent)).status_code == 403
    r = client.get("/api/admin/stats", headers=h(admin))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["coaches"] == 3
    assert data["exercises"] >= 30
    assert data["bookings"]["total"] == 0
    assert "模拟" in data["note"]


def test_booking_note_is_empty_not_literal_none(client):
    parent = login(client, PARENT_PHONE)
    b = new_booking(client, parent)
    assert b["note"] == ""


def test_remaining_read_endpoints(client):
    parent = login(client, PARENT_PHONE)
    coach = login(client, COACH_PHONE)
    assert client.get("/api/coaches/coach_wang", headers=h(parent)).status_code == 200
    services = client.get("/api/services", headers=h(parent))
    assert services.status_code == 200 and services.json()["data"]["total"] >= 5
    b = new_booking(client, parent)
    assert client.get(f"/api/bookings/{b['id']}", headers=h(parent)).status_code == 200
    # Seed now ships 2 demo family tasks (Motion Coach Mode B material for
    # c_xingxing + c_xiaoyue); the parent sees exactly those before creating more.
    assert client.get("/api/tasks", headers=h(parent)).json()["data"]["total"] == 2
    assert client.get("/api/videos", headers=h(parent)).status_code == 200

    assert client.post(f"/api/bookings/{b['id']}/accept", headers=h(coach), json={}).status_code == 200
    task = client.post(
        "/api/tasks", headers=h(coach),
        json={"childId": "c_xingxing", "title": "课后练习", "items": ["单脚站立"]},
    )
    assert task.status_code == 201, task.text
    tid = task.json()["data"]["id"]
    assert client.get(f"/api/tasks/{tid}/submissions", headers=h(parent)).status_code == 200
