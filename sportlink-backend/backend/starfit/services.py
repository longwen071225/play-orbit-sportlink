"""StarFit business logic. All writes must be executed inside db.transaction().

Order status is controlled exclusively here; there is no generic PATCH endpoint.
Booking amounts come from sf_service.priceCents, never from the request body.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .. import db
from ..agent import ApiError
from ..config import settings
from . import stars
from .auth import assert_child_access, coach_id_for_user

FIVE_DIMENSIONS = ["strength", "speed", "endurance", "coordination", "balance"]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"ACCEPTED", "CANCELLED", "REJECTED"},
    "ACCEPTED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
    "REJECTED": set(),
}


def _loads(text: Any, fallback: Any) -> Any:
    try:
        return json.loads(text) if text else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


def paginate(items: list[Any], page: int, page_size: int) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start : start + page_size],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "hasMore": start + page_size < total,
    }


def _ms(value: int | None) -> str | None:
    return db.ms_to_iso(value) if value else None


# ------------------------------------------------------------------ serializers
def child_out(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "guardianId": row["guardianId"],
        "nickname": row["nickname"],
        "age": row["age"],
        "sportsInterests": _loads(row["sportsInterests"], []),
        "trainingGoals": _loads(row["trainingGoals"], []),
        "photoConsent": bool(row["photoConsent"]),
        "createdAt": _ms(row["createdAt"]),
        "updatedAt": _ms(row["updatedAt"]),
    }


def coach_out(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "userId": row["userId"],
        "name": row["name"],
        "serviceAreas": _loads(row["serviceAreas"], []),
        "courseTypes": _loads(row["courseTypes"], []),
        "priceCents": row["priceCents"],
        "priceYuan": f"{row['priceCents'] / 100:.2f}",
        "bio": row["bio"],
        "certificateStatus": row["certificateStatus"],
        "avatarUrl": row["avatarUrl"],
        "createdAt": _ms(row["createdAt"]),
    }


def service_out(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "coachId": row["coachId"],
        "title": row["title"],
        "sportType": row["sportType"],
        "ageMin": row["ageMin"],
        "ageMax": row["ageMax"],
        "priceCents": row["priceCents"],
        "priceYuan": f"{row['priceCents'] / 100:.2f}",
        "durationMinutes": row["durationMinutes"],
        "description": row["description"],
        "status": row["status"],
        "createdAt": _ms(row["createdAt"]),
    }


def booking_out(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "parentId": row["parentId"],
        "childId": row["childId"],
        "coachId": row["coachId"],
        "serviceId": row["serviceId"],
        "startAt": _ms(row["startAt"]),
        "endAt": _ms(row["endAt"]),
        "status": row["status"],
        "paymentStatus": row["paymentStatus"],
        "amountCents": row["amountCents"],
        "amountYuan": f"{row['amountCents'] / 100:.2f}",
        "note": row["note"],
        "address": row["address"],
        "createdAt": _ms(row["createdAt"]),
        "updatedAt": _ms(row["updatedAt"]),
    }


def training_record_out(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "bookingId": row["bookingId"],
        "childId": row["childId"],
        "coachId": row["coachId"],
        "durationMinutes": row["durationMinutes"],
        "content": row["content"],
        "performance": _loads(row["performance"], {}),
        "createdAt": _ms(row["createdAt"]),
    }


def exercise_out(row: Any) -> dict[str, Any]:
    return {
        "exerciseId": row["id"],
        "name": row["name"],
        "category": row["category"],
        "minAge": row["minAge"],
        "maxAge": row["maxAge"],
        "difficulty": row["difficulty"],
        "trainingGoal": row["trainingGoal"],
        "instructions": _loads(row["instructions"], []),
        "commonMistakes": _loads(row["commonMistakes"], []),
        "equipment": _loads(row["equipment"], []),
        "safetyNotes": row["safetyNotes"],
        "videoUrl": row["videoUrl"],
        "model3dUrl": row["model3dUrl"],
        "tags": _loads(row["tags"], []),
    }


def task_out(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "childId": row["childId"],
        "bookingId": row["bookingId"],
        "coachId": row["coachId"],
        "title": row["title"],
        "items": _loads(row["itemsJson"], []),
        "goalCount": row["goalCount"],
        "status": row["status"],
        "createdAt": _ms(row["createdAt"]),
    }


def submission_out(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "taskId": row["taskId"],
        "parentId": row["parentId"],
        "content": row["content"],
        "photoUrls": _loads(row["photoUrls"], []),
        "status": row["status"],
        "coachFeedback": row["coachFeedback"],
        "createdAt": _ms(row["createdAt"]),
        "reviewedAt": _ms(row["reviewedAt"]),
    }


def video_out(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "exerciseId": row["exerciseId"],
        "ageMin": row["ageMin"],
        "ageMax": row["ageMax"],
        "videoUrl": row["videoUrl"],
        "thumbnailUrl": row["thumbnailUrl"],
        "durationSeconds": row["durationSeconds"],
        "createdAt": _ms(row["createdAt"]),
    }


# ------------------------------------------------------------------ children
def create_child(conn: Any, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    nickname = str(payload.get("nickname") or "").strip()
    age = int(payload.get("age", 0))
    if not nickname or len(nickname) > 30:
        raise ApiError(400, "VALIDATION_ERROR", "nickname 必填且不超过 30 字")
    if not 3 <= age <= 17:
        raise ApiError(400, "VALIDATION_ERROR", "age 必须在 3-17 之间")
    interests = payload.get("sportsInterests") or []
    goals = payload.get("trainingGoals") or []
    if not isinstance(interests, list) or not isinstance(goals, list):
        raise ApiError(400, "VALIDATION_ERROR", "sportsInterests / trainingGoals 必须是数组")

    now = db.now_ms()
    cid = db.new_id("c")
    conn.execute(
        'INSERT INTO "sf_child" '
        '("id","guardianId","nickname","age","sportsInterests","trainingGoals","createdAt","updatedAt") '
        "VALUES (?,?,?,?,?,?,?,?)",
        (cid, user["id"], nickname, age, json.dumps(interests, ensure_ascii=False),
         json.dumps(goals, ensure_ascii=False), now, now),
    )
    conn.execute(
        'INSERT INTO "sf_guardian_relationship" '
        '("id","childId","userId","relationship","createdAt") VALUES (?,?,?,?,?)',
        (db.new_id("gr"), cid, user["id"], "GUARDIAN", now),
    )
    row = conn.execute('SELECT * FROM "sf_child" WHERE "id"=?', (cid,)).fetchone()
    return child_out(row)


def list_children(conn: Any, user: dict[str, Any]) -> list[dict[str, Any]]:
    role = user["role"]
    if role == "ADMIN":
        rows = conn.execute('SELECT * FROM "sf_child" ORDER BY "createdAt"').fetchall()
    elif role == "COACH":
        coach_id = coach_id_for_user(conn, user)
        rows = conn.execute(
            'SELECT DISTINCT c.* FROM "sf_child" c JOIN "sf_booking" b ON b."childId"=c."id" '
            'WHERE b."coachId"=? AND b."status" IN (\'ACCEPTED\',\'IN_PROGRESS\',\'COMPLETED\') '
            'ORDER BY c."createdAt"',
            (coach_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT DISTINCT c.* FROM "sf_child" c LEFT JOIN "sf_guardian_relationship" g '
            'ON g."childId"=c."id" WHERE c."guardianId"=? OR g."userId"=? ORDER BY c."createdAt"',
            (user["id"], user["id"]),
        ).fetchall()
    return [child_out(r) for r in rows]


def get_child(conn: Any, user: dict[str, Any], child_id: str) -> dict[str, Any]:
    return child_out(assert_child_access(conn, user, child_id))


# ------------------------------------------------------------------ coaches / services / slots
def list_coaches(
    conn: Any, sport_type: str | None, area: str | None, available_on: str | None, page: int, page_size: int
) -> dict[str, Any]:
    rows = conn.execute(
        'SELECT * FROM "sf_coach" WHERE "certificateStatus"=\'APPROVED\' ORDER BY "name"'
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        types = _loads(row["courseTypes"], [])
        areas = _loads(row["serviceAreas"], [])
        if sport_type and sport_type not in types:
            continue
        if area and area not in areas:
            continue
        if available_on:
            try:
                day = date.fromisoformat(available_on)
            except ValueError:
                raise ApiError(400, "VALIDATION_ERROR", "availableOn 需为 YYYY-MM-DD")
            start = int(datetime(day.year, day.month, day.day, tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000)
            end = start + 24 * 3600 * 1000
            slot = conn.execute(
                'SELECT 1 FROM "sf_coach_availability" WHERE "coachId"=? AND "status"=\'OPEN\' '
                'AND "startAt">=? AND "startAt"<? LIMIT 1',
                (row["id"], start, end),
            ).fetchone()
            if not slot:
                continue
        out = coach_out(row)
        services = conn.execute(
            'SELECT * FROM "sf_service" WHERE "coachId"=? AND "status"=\'ACTIVE\' ORDER BY "createdAt"',
            (row["id"],),
        ).fetchall()
        out["services"] = [service_out(s) for s in services]
        items.append(out)
    return paginate(items, page, page_size)


def get_coach(conn: Any, coach_id: str) -> dict[str, Any]:
    row = conn.execute('SELECT * FROM "sf_coach" WHERE "id"=?', (coach_id,)).fetchone()
    if not row:
        raise ApiError(404, "COACH_NOT_FOUND", f"教练 {coach_id} 不存在")
    out = coach_out(row)
    out["services"] = [
        service_out(s)
        for s in conn.execute(
            'SELECT * FROM "sf_service" WHERE "coachId"=? AND "status"=\'ACTIVE\'', (coach_id,)
        ).fetchall()
    ]
    return out


def get_coach_slots(conn: Any, coach_id: str, from_date: str | None, to_date: str | None) -> dict[str, Any]:
    if not conn.execute('SELECT 1 FROM "sf_coach" WHERE "id"=?', (coach_id,)).fetchone():
        raise ApiError(404, "COACH_NOT_FOUND", f"教练 {coach_id} 不存在")
    params: list[Any] = [coach_id]
    sql = 'SELECT * FROM "sf_coach_availability" WHERE "coachId"=?'
    if from_date:
        try:
            d = date.fromisoformat(from_date)
            params.append(int(datetime(d.year, d.month, d.day, tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000))
            sql += ' AND "endAt">?'
        except ValueError:
            raise ApiError(400, "VALIDATION_ERROR", "from 需为 YYYY-MM-DD")
    if to_date:
        try:
            d = date.fromisoformat(to_date) + timedelta(days=1)
            params.append(int(datetime(d.year, d.month, d.day, tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000))
            sql += ' AND "startAt"<?'
        except ValueError:
            raise ApiError(400, "VALIDATION_ERROR", "to 需为 YYYY-MM-DD")
    sql += ' ORDER BY "startAt"'
    slots = conn.execute(sql, tuple(params)).fetchall()

    items = []
    for s in slots:
        conflict = conn.execute(
            'SELECT 1 FROM "sf_booking" WHERE "coachId"=? AND "status" NOT IN (\'CANCELLED\',\'REJECTED\') '
            'AND "startAt"<? AND "endAt">? LIMIT 1',
            (coach_id, s["endAt"], s["startAt"]),
        ).fetchone()
        items.append(
            {
                "slotId": s["id"],
                "coachId": coach_id,
                "startAt": _ms(s["startAt"]),
                "endAt": _ms(s["endAt"]),
                "status": "BOOKED" if conflict else s["status"],
            }
        )
    return {"coachId": coach_id, "total": len(items), "slots": items}


def list_services(conn: Any, sport_type: str | None, page: int, page_size: int) -> dict[str, Any]:
    sql = 'SELECT * FROM "sf_service" WHERE "status"=\'ACTIVE\''
    params: tuple[Any, ...] = ()
    if sport_type:
        sql += ' AND "sportType"=?'
        params = (sport_type,)
    sql += ' ORDER BY "createdAt"'
    return paginate([service_out(r) for r in conn.execute(sql, params).fetchall()], page, page_size)


# ------------------------------------------------------------------ bookings
def create_booking(conn: Any, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if user["role"] != "PARENT":
        raise ApiError(403, "FORBIDDEN", "仅家长可创建预约")
    child = assert_child_access(conn, user, str(payload.get("childId") or ""))
    service_row = conn.execute('SELECT * FROM "sf_service" WHERE "id"=?', (payload.get("serviceId"),)).fetchone()
    if not service_row or service_row["status"] != "ACTIVE":
        raise ApiError(404, "SERVICE_NOT_FOUND", "课程不存在或未上架")
    coach_row = conn.execute('SELECT * FROM "sf_coach" WHERE "id"=?', (service_row["coachId"],)).fetchone()
    if not coach_row or coach_row["certificateStatus"] != "APPROVED":
        raise ApiError(409, "COACH_NOT_APPROVED", "该教练尚未通过资质审核")
    if not service_row["ageMin"] <= child["age"] <= service_row["ageMax"]:
        raise ApiError(400, "AGE_OUT_OF_RANGE", f"课程适龄 {service_row['ageMin']}-{service_row['ageMax']} 岁")

    try:
        start_ms = db.iso_to_ms(str(payload["startAt"]))
        end_ms = db.iso_to_ms(str(payload["endAt"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise ApiError(400, "VALIDATION_ERROR", f"startAt / endAt 需为带时区的 ISO-8601：{exc}")
    if end_ms <= start_ms:
        raise ApiError(400, "VALIDATION_ERROR", "endAt 必须晚于 startAt")
    if end_ms - start_ms > 4 * 3600 * 1000:
        raise ApiError(400, "VALIDATION_ERROR", "单次课程不能超过 4 小时")

    slot = conn.execute(
        'SELECT 1 FROM "sf_coach_availability" WHERE "coachId"=? AND "status"=\'OPEN\' '
        'AND "startAt"<=? AND "endAt">=? LIMIT 1',
        (service_row["coachId"], start_ms, end_ms),
    ).fetchone()
    if not slot:
        raise ApiError(409, "SLOT_NOT_AVAILABLE", "所选时间不在教练开放档期内")

    conflict = conn.execute(
        'SELECT "id" FROM "sf_booking" WHERE "coachId"=? AND "status" NOT IN (\'CANCELLED\',\'REJECTED\') '
        'AND "startAt"<? AND "endAt">? LIMIT 1',
        (service_row["coachId"], end_ms, start_ms),
    ).fetchone()
    if conflict:
        raise ApiError(409, "BOOKING_CONFLICT", f"该教练在此时间段已有预约（{conflict['id']}）")

    now = db.now_ms()
    bid = db.new_id("bk")
    conn.execute(
        'INSERT INTO "sf_booking" '
        '("id","parentId","childId","coachId","serviceId","startAt","endAt","status",'
        '"paymentStatus","amountCents","note","address","createdAt","updatedAt") '
        "VALUES (?,?,?,?,?,?,?,'PENDING','SIMULATED_UNPAID',?,?,?,?,?)",
        (bid, user["id"], child["id"], service_row["coachId"], service_row["id"],
         start_ms, end_ms, service_row["priceCents"], str(payload.get("note") or "")[:500],
         str(payload.get("address") or "")[:500], now, now),
    )
    audit_event(conn, user, "booking", bid, "created", "家长创建预约")
    return booking_out(conn.execute('SELECT * FROM "sf_booking" WHERE "id"=?', (bid,)).fetchone())


def _visible_booking(conn: Any, user: dict[str, Any], booking_id: str) -> Any:
    row = conn.execute('SELECT * FROM "sf_booking" WHERE "id"=?', (booking_id,)).fetchone()
    if not row:
        raise ApiError(404, "BOOKING_NOT_FOUND", f"订单 {booking_id} 不存在")
    role = user["role"]
    if role == "PARENT" and row["parentId"] != user["id"]:
        raise ApiError(403, "FORBIDDEN", "只能查看自己的订单")
    if role == "COACH" and row["coachId"] != coach_id_for_user(conn, user):
        raise ApiError(403, "FORBIDDEN", "只能查看自己课程的订单")
    if role not in ("PARENT", "COACH", "ADMIN"):
        raise ApiError(403, "FORBIDDEN", "无权查看订单")
    return row


def list_bookings(conn: Any, user: dict[str, Any], status: str | None, page: int, page_size: int) -> dict[str, Any]:
    sql = 'SELECT * FROM "sf_booking"'
    clauses: list[str] = []
    params: list[Any] = []
    if user["role"] == "PARENT":
        clauses.append('"parentId"=?')
        params.append(user["id"])
    elif user["role"] == "COACH":
        clauses.append('"coachId"=?')
        params.append(coach_id_for_user(conn, user))
    elif user["role"] != "ADMIN":
        raise ApiError(403, "FORBIDDEN", "无权查看订单")
    if status:
        clauses.append('"status"=?')
        params.append(status)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += ' ORDER BY "createdAt" DESC'
    return paginate([booking_out(r) for r in conn.execute(sql, tuple(params)).fetchall()], page, page_size)


def get_booking(conn: Any, user: dict[str, Any], booking_id: str) -> dict[str, Any]:
    return booking_out(_visible_booking(conn, user, booking_id))


def audit_event(conn: Any, user: dict[str, Any], entity_type: str, entity_id: str,
                action: str, reason: str = "") -> None:
    conn.execute(
        'INSERT INTO "sf_portal_audit" '
        '("id","entityType","entityId","action","actorId","actorName","reason","createdAt") '
        'VALUES (?,?,?,?,?,?,?,?)',
        (db.new_id("audit"), entity_type, entity_id, action, user["id"],
         user.get("name", user["role"]), reason[:2000], db.now_ms()),
    )


def transition_booking(
    conn: Any, user: dict[str, Any], booking_id: str, target: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    row = _visible_booking(conn, user, booking_id)
    current = row["status"]
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ApiError(409, "INVALID_STATE_TRANSITION", f"订单状态不能从 {current} 变更为 {target}")

    if target in ("ACCEPTED", "IN_PROGRESS", "COMPLETED"):
        if user["role"] != "COACH" or row["coachId"] != coach_id_for_user(conn, user):
            raise ApiError(403, "FORBIDDEN", "接单、开课与完成课程只能由该订单教练操作")
    if target in ("ACCEPTED", "IN_PROGRESS"):
        coach = conn.execute('SELECT "certificateStatus" FROM "sf_coach" WHERE "id"=?', (row["coachId"],)).fetchone()
        if not coach or coach["certificateStatus"] != "APPROVED":
            raise ApiError(403, "COACH_NOT_APPROVED", "教练未通过审核或已暂停服务，不能接单或开课")
    if target == "REJECTED" and user["role"] != "COACH":
        raise ApiError(403, "FORBIDDEN", "仅订单教练可拒绝预约")
    if target == "CANCELLED" and user["role"] not in ("PARENT", "COACH", "ADMIN"):
        raise ApiError(403, "FORBIDDEN", "无权取消订单")

    if target == "COMPLETED":
        record = conn.execute(
            'SELECT 1 FROM "sf_training_record" WHERE "bookingId"=? LIMIT 1', (booking_id,)
        ).fetchone()
        if not record:
            raise ApiError(409, "TRAINING_RECORD_REQUIRED", "完成课程前必须先提交真实训练记录")

    now = db.now_ms()
    payment = row["paymentStatus"]
    if target == "ACCEPTED":
        payment = "SIMULATED_PAID"  # simulated only, no real charge
    conn.execute(
        'UPDATE "sf_booking" SET "status"=?, "paymentStatus"=?, "updatedAt"=? WHERE "id"=?',
        (target, payment, now, booking_id),
    )
    audit_event(conn, user, "booking", booking_id, target.lower(),
                str((payload or {}).get("reason") or (payload or {}).get("note") or ""))
    updated = conn.execute('SELECT * FROM "sf_booking" WHERE "id"=?', (booking_id,)).fetchone()

    awarded: list[dict[str, Any]] = []
    if target == "COMPLETED":
        service = conn.execute('SELECT * FROM "sf_service" WHERE "id"=?', (row["serviceId"],)).fetchone()
        awarded = stars.award_for_completed_booking(conn, dict(updated), dict(service) if service else {})

    return {
        "booking": booking_out(updated),
        "starsAwarded": awarded,
        "note": str((payload or {}).get("note") or "")[:500],
    }


# ------------------------------------------------------------------ training records
def create_training_record(conn: Any, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    coach_id = coach_id_for_user(conn, user)
    booking_id = str(payload.get("bookingId") or "")
    row = conn.execute('SELECT * FROM "sf_booking" WHERE "id"=?', (booking_id,)).fetchone()
    if not row:
        raise ApiError(404, "BOOKING_NOT_FOUND", f"订单 {booking_id} 不存在")
    if row["coachId"] != coach_id:
        raise ApiError(403, "FORBIDDEN", "只能为自己课程的订单记录训练")
    if row["status"] not in ("ACCEPTED", "IN_PROGRESS", "COMPLETED"):
        raise ApiError(409, "INVALID_STATE_TRANSITION", "订单尚未接单，不能记录训练")

    content = str(payload.get("content") or "").strip()
    if not content or len(content) > 2000:
        raise ApiError(400, "VALIDATION_ERROR", "content 必填且不超过 2000 字")
    duration = int(payload.get("durationMinutes", 0))
    if not 1 <= duration <= 240:
        raise ApiError(400, "VALIDATION_ERROR", "durationMinutes 必须在 1-240 之间")
    performance = payload.get("performance") or {}
    if not isinstance(performance, dict):
        raise ApiError(400, "VALIDATION_ERROR", "performance 必须是对象")
    # Body metrics are NEVER inferred here. Only coach-entered observations pass through.
    for key in performance:
        if key not in FIVE_DIMENSIONS and key not in ("notes", "source", "actions", "grade", "feedback"):
            raise ApiError(400, "VALIDATION_ERROR", f"performance 不允许字段 {key}")

    rid = db.new_id("tr")
    now = db.now_ms()
    conn.execute(
        'INSERT INTO "sf_training_record" '
        '("id","bookingId","childId","coachId","durationMinutes","content","performance","createdAt") '
        "VALUES (?,?,?,?,?,?,?,?)",
        (rid, booking_id, row["childId"], coach_id, duration, content,
         json.dumps(performance, ensure_ascii=False), now),
    )
    audit_event(conn, user, "booking", booking_id, "training_record_saved")
    return training_record_out(conn.execute('SELECT * FROM "sf_training_record" WHERE "id"=?', (rid,)).fetchone())


def list_training_records(
    conn: Any, user: dict[str, Any], child_id: str, page: int, page_size: int
) -> dict[str, Any]:
    assert_child_access(conn, user, child_id)
    sql = 'SELECT * FROM "sf_training_record" WHERE "childId"=?'
    params: list[Any] = [child_id]
    if user["role"] == "COACH":
        sql += ' AND "coachId"=?'
        params.append(coach_id_for_user(conn, user))
    rows = conn.execute(sql + ' ORDER BY "createdAt" DESC', params).fetchall()
    return paginate([training_record_out(r) for r in rows], page, page_size)


# ------------------------------------------------------------------ exercise knowledge base
def list_exercises(
    conn: Any, category: str | None, keyword: str | None, age: int | None, page: int, page_size: int
) -> dict[str, Any]:
    rows = conn.execute('SELECT * FROM "sf_exercise" ORDER BY "category","id"').fetchall()
    items = []
    for r in rows:
        if category and r["category"] != category:
            continue
        if age is not None and not (r["minAge"] <= age <= r["maxAge"]):
            continue
        if keyword:
            hay = f"{r['name']}{r['trainingGoal']}{r['tags']}{r['category']}"
            if keyword not in hay:
                continue
        items.append(exercise_out(r))
    return paginate(items, page, page_size)


def get_exercise(conn: Any, exercise_id: str) -> dict[str, Any]:
    row = conn.execute('SELECT * FROM "sf_exercise" WHERE "id"=?', (exercise_id,)).fetchone()
    if not row:
        raise ApiError(404, "EXERCISE_NOT_FOUND", f"动作 {exercise_id} 不存在")
    return exercise_out(row)


# ------------------------------------------------------------------ family tasks
def create_task(conn: Any, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    coach_id = coach_id_for_user(conn, user)
    child_id = str(payload.get("childId") or "")
    assert_child_access(conn, user, child_id)
    if payload.get("bookingId"):
        booking = _visible_booking(conn, user, str(payload["bookingId"]))
        if booking["childId"] != child_id:
            raise ApiError(400, "VALIDATION_ERROR", "任务儿童与预约儿童不一致")
    title = str(payload.get("title") or "").strip()
    if not title or len(title) > 100:
        raise ApiError(400, "VALIDATION_ERROR", "title 必填且不超过 100 字")
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise ApiError(400, "VALIDATION_ERROR", "items 必须是非空数组")
    goal = int(payload.get("goalCount") or len(items))
    if not 1 <= goal <= 20:
        raise ApiError(400, "VALIDATION_ERROR", "goalCount 必须在 1-20 之间")

    tid = db.new_id("ft")
    now = db.now_ms()
    conn.execute(
        'INSERT INTO "sf_family_task" '
        '("id","childId","bookingId","coachId","title","itemsJson","goalCount","status","createdAt") '
        "VALUES (?,?,?,?,?,?,?,'OPEN',?)",
        (tid, child_id, payload.get("bookingId"), coach_id, title,
         json.dumps(items, ensure_ascii=False), goal, now),
    )
    return task_out(conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (tid,)).fetchone())


def list_tasks(
    conn: Any, user: dict[str, Any], child_id: str | None, page: int, page_size: int
) -> dict[str, Any]:
    if child_id:
        assert_child_access(conn, user, child_id)
        sql = 'SELECT * FROM "sf_family_task" WHERE "childId"=?'
        params: list[Any] = [child_id]
        if user["role"] == "COACH":
            sql += ' AND "coachId"=?'
            params.append(coach_id_for_user(conn, user))
        rows = conn.execute(sql + ' ORDER BY "createdAt" DESC', params).fetchall()
    elif user["role"] == "COACH":
        coach_id = coach_id_for_user(conn, user)
        rows = conn.execute(
            'SELECT * FROM "sf_family_task" WHERE "coachId"=? ORDER BY "createdAt" DESC', (coach_id,)
        ).fetchall()
    elif user["role"] == "PARENT":
        rows = conn.execute(
            'SELECT t.* FROM "sf_family_task" t JOIN "sf_child" c ON c."id"=t."childId" '
            'LEFT JOIN "sf_guardian_relationship" g ON g."childId"=c."id" '
            'WHERE c."guardianId"=? OR g."userId"=? ORDER BY t."createdAt" DESC',
            (user["id"], user["id"]),
        ).fetchall()
    else:
        rows = conn.execute('SELECT * FROM "sf_family_task" ORDER BY "createdAt" DESC').fetchall()
    return paginate([task_out(r) for r in rows], page, page_size)


def submit_task(conn: Any, user: dict[str, Any], task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if user["role"] != "PARENT":
        raise ApiError(403, "FORBIDDEN", "仅家长可提交家庭任务完成记录")
    task = conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone()
    if not task:
        raise ApiError(404, "TASK_NOT_FOUND", f"任务 {task_id} 不存在")
    assert_child_access(conn, user, task["childId"])
    photos = payload.get("photoUrls") or []
    if not isinstance(photos, list):
        raise ApiError(400, "VALIDATION_ERROR", "photoUrls 必须是数组")
    sid = db.new_id("ts")
    now = db.now_ms()
    conn.execute(
        'INSERT INTO "sf_task_submission" '
        '("id","taskId","parentId","content","photoUrls","status","coachFeedback","createdAt","reviewedAt") '
        "VALUES (?,?,?,?,?,'SUBMITTED','',?,NULL)",
        (sid, task_id, user["id"], str(payload.get("content") or "")[:1000],
         json.dumps(photos, ensure_ascii=False), now),
    )
    conn.execute('UPDATE "sf_family_task" SET "status"=\'SUBMITTED\' WHERE "id"=?', (task_id,))
    return {
        "submission": submission_out(conn.execute('SELECT * FROM "sf_task_submission" WHERE "id"=?', (sid,)).fetchone()),
        "starsAwarded": [],
        "note": "提交后需教练确认，确认完成时才发放成长星星",
    }


def confirm_task(
    conn: Any, user: dict[str, Any], task_id: str, submission_id: str, feedback: str
) -> dict[str, Any]:
    coach_id = coach_id_for_user(conn, user)
    task = conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone()
    if not task:
        raise ApiError(404, "TASK_NOT_FOUND", f"任务 {task_id} 不存在")
    if task["coachId"] != coach_id:
        raise ApiError(403, "FORBIDDEN", "只能确认自己布置的任务")
    sub = conn.execute(
        'SELECT * FROM "sf_task_submission" WHERE "id"=? AND "taskId"=?', (submission_id, task_id)
    ).fetchone()
    if not sub:
        raise ApiError(404, "SUBMISSION_NOT_FOUND", "提交记录不存在")
    now = db.now_ms()
    conn.execute(
        'UPDATE "sf_task_submission" SET "status"=\'CONFIRMED\', "coachFeedback"=?, "reviewedAt"=? WHERE "id"=?',
        (str(feedback)[:1000], now, submission_id),
    )
    conn.execute('UPDATE "sf_family_task" SET "status"=\'CONFIRMED\' WHERE "id"=?', (task_id,))
    star = stars.award_star(conn, task["childId"], "HOME_CHALLENGE", "TASK", task_id)
    return {
        "task": task_out(conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone()),
        "submission": submission_out(conn.execute('SELECT * FROM "sf_task_submission" WHERE "id"=?', (submission_id,)).fetchone()),
        "starsAwarded": [star] if star else [],
    }


def list_submissions(conn: Any, user: dict[str, Any], task_id: str) -> dict[str, Any]:
    task = conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone()
    if not task:
        raise ApiError(404, "TASK_NOT_FOUND", f"任务 {task_id} 不存在")
    assert_child_access(conn, user, task["childId"])
    if user["role"] == "COACH" and task["coachId"] != coach_id_for_user(conn, user):
        raise ApiError(403, "FORBIDDEN", "只能查看自己布置任务的提交记录")
    rows = conn.execute(
        'SELECT * FROM "sf_task_submission" WHERE "taskId"=? ORDER BY "createdAt"', (task_id,)
    ).fetchall()
    return {"taskId": task_id, "total": len(rows), "submissions": [submission_out(r) for r in rows]}


def list_motion_exercises(conn: Any) -> list[dict[str, Any]]:
    """Motion-enabled exercises with their rule-engine config for the frontend."""
    from . import pose as pose_engine

    rows = conn.execute('SELECT * FROM "sf_exercise" ORDER BY "category","id"').fetchall()
    return [
        {**exercise_out(r), "motionConfig": pose_engine.MOTION_CONFIGS[r["id"]]}
        for r in rows
        if r["id"] in pose_engine.MOTION_CONFIGS
    ]


# ------------------------------------------------------------------ motion coach training sessions
def training_result_out(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "sessionId": row["sessionId"],
        "childId": row["childId"],
        "exerciseId": row["exerciseId"],
        "taskId": row["taskId"],
        "durationSeconds": row["durationSeconds"],
        "repCount": row["repCount"],
        "validRepCount": row["validRepCount"],
        "holdSeconds": round(row["holdMs"] / 1000.0, 1),
        "errorCounts": _loads(row["errorCountsJson"], {}),
        "avgConfidence": row["avgConfidence"],
        "completed": bool(row["completed"]),
        "starAwarded": bool(row["starAwarded"]),
        "summary": row["summary"],
        "createdAt": _ms(row["createdAt"]),
    }


def _session_row(conn: Any, user: dict[str, Any], session_id: str) -> Any:
    row = conn.execute('SELECT * FROM "sf_training_session" WHERE "id"=?', (session_id,)).fetchone()
    if not row:
        raise ApiError(404, "TRAINING_SESSION_NOT_FOUND", f"训练会话 {session_id} 不存在")
    if row["userId"] != user["id"] and user["role"] != "ADMIN":
        if user["role"] != "COACH":
            raise ApiError(403, "FORBIDDEN", "无权访问该训练会话")
        assert_child_access(conn, user, row["childId"])  # coach must still have a real relationship
    return row


def _session_targets(row: Any) -> tuple[int | None, int | None]:
    reps = int(row["targetReps"] or 0)
    seconds = int(row["targetSeconds"] or 0)
    return (reps or None), (seconds or None)


def training_session_out(conn: Any, row: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    from . import pose as pose_engine

    config = config or pose_engine.MOTION_CONFIGS.get(row["exerciseId"]) or {}
    counters = {
        "repCount": row["repCount"], "validRepCount": row["validRepCount"], "holdMs": row["holdMs"],
        "errorCounts": _loads(row["errorCountsJson"], {}), "avgConfidence": row["avgConfidence"],
        "poseLostCount": row["poseLostCount"],
    }
    target_reps, target_seconds = _session_targets(row)
    exercise = conn.execute('SELECT "name" FROM "sf_exercise" WHERE "id"=?', (row["exerciseId"],)).fetchone()
    result = conn.execute('SELECT * FROM "sf_training_result" WHERE "sessionId"=?', (row["id"],)).fetchone()
    return {
        "id": row["id"],
        "childId": row["childId"],
        "userId": row["userId"],
        "taskId": row["taskId"],
        "exerciseId": row["exerciseId"],
        "exerciseName": exercise["name"] if exercise else row["exerciseId"],
        "mode": row["mode"],
        "status": row["status"],
        "counters": pose_engine.counters_out(counters, config, target_reps, target_seconds),
        "startedAt": _ms(row["startedAt"]),
        "endedAt": _ms(row["endedAt"]),
        "result": training_result_out(result) if result else None,
    }


def list_training_sessions(
    conn: Any, user: dict[str, Any], child_id: str, page: int, page_size: int
) -> dict[str, Any]:
    assert_child_access(conn, user, child_id)
    rows = conn.execute(
        'SELECT * FROM "sf_training_session" WHERE "childId"=? ORDER BY "startedAt" DESC', (child_id,)
    ).fetchall()
    return paginate([training_session_out(conn, r) for r in rows], page, page_size)


def create_training_session(conn: Any, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    from . import pose as pose_engine

    child_id = str(payload.get("childId") or "")
    assert_child_access(conn, user, child_id)
    exercise_id = str(payload.get("exerciseId") or "")
    exercise = conn.execute('SELECT * FROM "sf_exercise" WHERE "id"=?', (exercise_id,)).fetchone()
    if not exercise:
        raise ApiError(404, "EXERCISE_NOT_FOUND", f"动作 {exercise_id} 不在知识库中")
    config = pose_engine.MOTION_CONFIGS.get(exercise_id)
    if not config:
        raise ApiError(
            400, "NOT_MOTION_ENABLED",
            f"动作 {exercise['name']} 暂不支持姿态识别训练，可在知识库查看动作说明",
        )

    task_id = payload.get("taskId") or None
    if task_id:
        task = conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone()
        if not task:
            raise ApiError(404, "TASK_NOT_FOUND", f"家庭任务 {task_id} 不存在")
        if task["childId"] != child_id:
            raise ApiError(400, "TASK_CHILD_MISMATCH", "该家庭任务不属于这个儿童档案")

    mode = str(payload.get("mode") or "POSE").upper()
    if mode not in ("POSE", "GUIDED"):
        raise ApiError(400, "VALIDATION_ERROR", "mode 仅支持 POSE 或 GUIDED")

    completion = config.get("completion", {})
    target_reps = int(completion.get("reps") or 0)
    target_seconds = int(completion.get("seconds") or 0)
    if completion.get("type") == "REPS":
        requested = payload.get("targetReps")
        if requested is not None:
            target_reps = max(1, min(int(requested), target_reps * 3))
        target_seconds = 0
    elif completion.get("type") == "HOLD":
        requested = payload.get("targetSeconds")
        if requested is not None:
            target_seconds = max(5, min(int(requested), target_seconds * 3))
        target_reps = 0

    sid = db.new_id("tss")
    now = db.now_ms()
    conn.execute(
        'INSERT INTO "sf_training_session" '
        '("id","childId","userId","taskId","exerciseId","mode","status","targetReps","targetSeconds",'
        '"repCount","validRepCount","holdMs","eventCount","errorCountsJson","avgConfidence","poseLostCount",'
        '"startedAt","endedAt","updatedAt") '
        "VALUES (?,?,?,?,?,?, 'ACTIVE', ?,?,0,0,0,0,'{}',0,0,?,NULL,?)",
        (sid, child_id, user["id"], task_id, exercise_id, mode,
         target_reps, target_seconds, now, now),
    )
    return training_session_out(conn, conn.execute(
        'SELECT * FROM "sf_training_session" WHERE "id"=?', (sid,)
    ).fetchone(), config)


def add_pose_feedback(
    conn: Any, user: dict[str, Any], session_id: str, events: list[dict[str, Any]]
) -> dict[str, Any]:
    from . import pose as pose_engine

    row = _session_row(conn, user, session_id)
    if row["status"] != "ACTIVE":
        raise ApiError(409, "TRAINING_SESSION_NOT_ACTIVE", "训练会话已结束，不能再上报动作反馈")
    if not isinstance(events, list) or not events:
        raise ApiError(400, "VALIDATION_ERROR", "events 必须是非空数组")
    events = events[: settings.POSE_MAX_EVENTS_PER_REQUEST]

    config = pose_engine.MOTION_CONFIGS.get(row["exerciseId"]) or {}
    counters = {
        "repCount": row["repCount"], "validRepCount": row["validRepCount"], "holdMs": row["holdMs"],
        "errorCounts": _loads(row["errorCountsJson"], {}), "avgConfidence": row["avgConfidence"],
        "poseLostCount": row["poseLostCount"],
    }
    outcome = pose_engine.apply_events(config, counters, events, db.now_ms())
    new_counters = outcome["counters"]

    now = db.now_ms()
    for event, verdict in zip(events, outcome["verdicts"]):
        if not isinstance(event, dict) or not verdict.get("ok"):
            continue
        metrics = event.get("metrics") if isinstance(event.get("metrics"), dict) else {}
        conn.execute(
            'INSERT INTO "sf_pose_feedback_event" '
            '("id","sessionId","childId","exerciseId","type","code","confidence","metricsJson","clientMs","createdAt") '
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (db.new_id("pfe"), session_id, row["childId"], row["exerciseId"],
             str(verdict.get("type", "")), str(verdict.get("code", "")),
             event.get("confidence"), json.dumps(metrics, ensure_ascii=False),
             event.get("clientMs"), now),
        )
    conn.execute(
        'UPDATE "sf_training_session" SET '
        '"repCount"=?, "validRepCount"=?, "holdMs"=?, "eventCount"=?, "errorCountsJson"=?, '
        '"avgConfidence"=?, "poseLostCount"=?, "updatedAt"=? WHERE "id"=?',
        (new_counters["repCount"], new_counters["validRepCount"], new_counters["holdMs"],
         new_counters["eventCount"], json.dumps(new_counters["errorCounts"], ensure_ascii=False),
         new_counters["avgConfidence"], new_counters["poseLostCount"], now, session_id),
    )
    return {
        "sessionId": session_id,
        "counters": pose_engine.counters_out(new_counters, config, *_session_targets(row)),
        "progressRatio": pose_engine.progress_ratio(config, new_counters, *_session_targets(row)),
        "completionCheck": pose_engine.evaluate_completion(config, new_counters, *_session_targets(row)),
        "accepted": outcome["accepted"],
        "rejected": [
            {"index": i, "reason": v.get("reason"), "type": v.get("type"), "code": v.get("code")}
            for i, v in enumerate(outcome["verdicts"]) if not v.get("ok")
        ],
    }


def complete_training_session(conn: Any, user: dict[str, Any], session_id: str) -> dict[str, Any]:
    """Backend-verified completion. The frontend has no 'completed' flag to send:
    truth comes from validated engine events only, and one session can only ever
    produce one result row and one growth star."""
    from . import pose as pose_engine
    from . import stars as star_rules

    row = _session_row(conn, user, session_id)
    config = pose_engine.MOTION_CONFIGS.get(row["exerciseId"]) or {}

    existing = conn.execute(
        'SELECT * FROM "sf_training_result" WHERE "sessionId"=?', (session_id,)
    ).fetchone()
    if existing:
        return {
            "result": training_result_out(existing),
            "starsAwarded": _stars_for_result(conn, existing["id"]),
            "idempotent": True,
        }

    if row["status"] != "ACTIVE":
        raise ApiError(409, "TRAINING_SESSION_NOT_ACTIVE", "训练会话已结束")

    counters = {
        "repCount": row["repCount"], "validRepCount": row["validRepCount"], "holdMs": row["holdMs"],
        "errorCounts": _loads(row["errorCountsJson"], {}), "avgConfidence": row["avgConfidence"],
    }
    check = pose_engine.evaluate_completion(config, counters, *_session_targets(row))
    if not check["met"]:
        raise ApiError(
            422, "TRAINING_REQUIREMENTS_NOT_MET",
            f"尚未达标：需要 {check['required']} {check['unit']}，当前 {check['actual']} {check['unit']}。继续加油！",
        )

    now = db.now_ms()
    duration = max(0, min(int((now - row["startedAt"]) / 1000), 7200))
    rid = db.new_id("trs")
    conn.execute(
        'INSERT INTO "sf_training_result" '
        '("id","sessionId","childId","exerciseId","taskId","durationSeconds","repCount","validRepCount",'
        '"holdMs","errorCountsJson","avgConfidence","completed","starAwarded","summary","createdAt") '
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,0,'',?)",
        (rid, session_id, row["childId"], row["exerciseId"], row["taskId"], duration,
         row["repCount"], row["validRepCount"], row["holdMs"], row["errorCountsJson"],
         row["avgConfidence"], now),
    )
    star = star_rules.award_star(conn, row["childId"], "HOME_TRAINING", "TRAINING_RESULT", rid)
    conn.execute('UPDATE "sf_training_result" SET "starAwarded"=? WHERE "id"=?', (1 if star else 0, rid))
    conn.execute(
        'UPDATE "sf_training_session" SET "status"=\'COMPLETED\', "endedAt"=?, "updatedAt"=? WHERE "id"=?',
        (now, now, session_id),
    )
    result = conn.execute('SELECT * FROM "sf_training_result" WHERE "id"=?', (rid,)).fetchone()
    return {
        "result": training_result_out(result),
        "starsAwarded": [star] if star else _stars_for_result(conn, rid),
        "idempotent": False,
    }


def _stars_for_result(conn: Any, result_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        'SELECT * FROM "sf_growth_star" WHERE "sourceType"=? AND "sourceId"=?',
        ("TRAINING_RESULT", result_id),
    ).fetchall()
    return [
        {
            "id": r["id"], "starType": r["starType"], "title": r["title"],
            "description": r["description"], "earnedAt": _ms(r["earnedAt"]),
            "metadata": _loads(r["metadataJson"], {}),
        }
        for r in rows
    ]


# ------------------------------------------------------------------ videos / stars / stats
def list_videos(conn: Any, category: str | None, page: int, page_size: int) -> dict[str, Any]:
    sql = 'SELECT * FROM "sf_video"'
    params: tuple[Any, ...] = ()
    if category:
        sql += ' WHERE "category"=?'
        params = (category,)
    sql += ' ORDER BY "createdAt"'
    return paginate([video_out(r) for r in conn.execute(sql, params).fetchall()], page, page_size)


def get_stars(conn: Any, user: dict[str, Any], child_id: str) -> dict[str, Any]:
    assert_child_access(conn, user, child_id)
    return stars.stars_for_child(conn, child_id, user["id"] if user["role"] == "PARENT" else None)


def mark_growth_event_seen(conn: Any, user: dict[str, Any], event_id: str) -> None:
    star = conn.execute('SELECT "childId" FROM "sf_growth_star" WHERE "id"=?', (event_id,)).fetchone()
    if not star:
        raise ApiError(404, "GROWTH_EVENT_NOT_FOUND", "成长事件不存在")
    assert_child_access(conn, user, star["childId"])
    conn.execute(
        'INSERT INTO "sf_growth_star_seen" ("starId","userId","seenAt") VALUES (?,?,?) '
        'ON CONFLICT ("starId","userId") DO NOTHING',
        (event_id, user["id"], db.now_ms()),
    )


def admin_stats(conn: Any) -> dict[str, Any]:
    def scalar(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0] or 0)

    by_status = {
        r["status"]: r["n"]
        for r in conn.execute('SELECT "status", COUNT(*) AS n FROM "sf_booking" GROUP BY "status"')
    }
    return {
        "users": scalar('SELECT COUNT(*) FROM "sf_user"'),
        "children": scalar('SELECT COUNT(*) FROM "sf_child"'),
        "coaches": scalar('SELECT COUNT(*) FROM "sf_coach"'),
        "services": scalar('SELECT COUNT(*) FROM "sf_service"'),
        "bookings": {"total": scalar('SELECT COUNT(*) FROM "sf_booking"'), "byStatus": by_status},
        "trainingRecords": scalar('SELECT COUNT(*) FROM "sf_training_record"'),
        "growthStars": scalar('SELECT COUNT(*) FROM "sf_growth_star"'),
        "exercises": scalar('SELECT COUNT(*) FROM "sf_exercise"'),
        "familyTasks": scalar('SELECT COUNT(*) FROM "sf_family_task"'),
        "revenueSimulatedCents": scalar(
            'SELECT COALESCE(SUM("amountCents"),0) FROM "sf_booking" WHERE "paymentStatus"=\'SIMULATED_PAID\''
        ),
        "note": "金额为模拟支付统计，未接入任何真实扣款",
    }
