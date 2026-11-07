"""Growth-star rules and idempotent awarding.

Rules are evaluated ONLY from persisted completions (bookings, confirmed task
submissions, and verified training sessions). The model can never mint a star. Two unique constraints
(sf_reward_event and sf_growth_star) plus an in-transaction existence check
guarantee one source event can never award the same star twice.
"""
from __future__ import annotations

import json
import math
from typing import Any

from .. import db

DISCLAIMER = "成长星星记录已完成的课程、家庭任务与陪练，不构成医学诊断或体能评估结论。"

STAR_DEFS: dict[str, dict[str, str]] = {
    "FIRST_COURSE": {
        "title": "启明星",
        "description": "完成首次上门体育课程，正式开启运动旅程",
        "color": "#FFD166",
        "constellation": "启程座",
        "stage": "起步",
        "animation": "ignite",
    },
    "BALANCE": {
        "title": "平衡星",
        "description": "完成一次平衡类训练课程",
        "color": "#8EC5FF",
        "constellation": "均衡座",
        "stage": "探索",
        "animation": "orbit",
    },
    "BASKETBALL": {
        "title": "篮球星",
        "description": "完成一次篮球基础训练课程",
        "color": "#FF9F68",
        "constellation": "跃动座",
        "stage": "探索",
        "animation": "bounce",
    },
    "COURSE_COMPLETED": {
        "title": "训练星",
        "description": "完成一次由教练记录的运动课程",
        "color": "#B5D66E",
        "constellation": "训练座",
        "stage": "探索",
        "animation": "ignite",
    },
    "HOME_CHALLENGE": {
        "title": "挑战星",
        "description": "完成教练布置并经确认的家庭运动任务",
        "color": "#B39DFF",
        "constellation": "坚持座",
        "stage": "进阶",
        "animation": "pulse",
    },
    "HOME_TRAINING": {
        "title": "陪练星",
        "description": "在 AI 运动陪练监督下完成一次达标家庭训练",
        "color": "#7BE3C3",
        "constellation": "自律座",
        "stage": "进阶",
        "animation": "pulse",
    },
}


def _position(index: int) -> dict[str, float]:
    """Deterministic golden-angle layout so the frontend can render directly."""
    angle = math.radians(index * 137.5)
    radius = 8.0 + 7.5 * math.sqrt(index)
    return {
        "x": round(50.0 + radius * math.cos(angle), 2),
        "y": round(50.0 + radius * math.sin(angle), 2),
    }


def award_star(
    conn: Any,
    child_id: str,
    star_type: str,
    source_type: str,
    source_id: str,
    event_type: str | None = None,
) -> dict[str, Any] | None:
    """Award once. Caller MUST hold a BEGIN IMMEDIATE transaction (db.transaction).

    Returns the created star row, or None when this source was already rewarded.
    """
    if star_type not in STAR_DEFS:
        raise ValueError(f"未知 star_type: {star_type}")
    event = event_type or f"STAR_{star_type}"
    already = conn.execute(
        'SELECT 1 FROM "sf_reward_event" WHERE "childId"=? AND "eventType"=? '
        'AND "sourceType"=? AND "sourceId"=?',
        (child_id, event, source_type, source_id),
    ).fetchone()
    if already:
        return None

    now = db.now_ms()
    defn = STAR_DEFS[star_type]
    star_id = db.new_id("st")
    metadata = {k: defn[k] for k in ("color", "constellation", "stage", "animation")}
    conn.execute(
        'INSERT INTO "sf_reward_event" '
        '("id","childId","eventType","sourceType","sourceId","starsAwarded","createdAt") '
        "VALUES (?,?,?,?,?,1,?)",
        (db.new_id("re"), child_id, event, source_type, source_id, now),
    )
    conn.execute(
        'INSERT OR IGNORE INTO "sf_growth_star" '
        '("id","childId","starType","title","description","sourceType","sourceId",'
        '"earnedAt","metadataJson") VALUES (?,?,?,?,?,?,?,?,?)',
        (star_id, child_id, star_type, defn["title"], defn["description"],
         source_type, source_id, now, json.dumps(metadata, ensure_ascii=False)),
    )
    return {
        "starId": star_id,
        "childId": child_id,
        "starType": star_type,
        "title": defn["title"],
        "description": defn["description"],
        "sourceType": source_type,
        "sourceId": source_id,
        "earnedAt": db.ms_to_iso(now),
        "metadata": metadata,
    }


def award_for_completed_booking(conn: Any, booking: dict[str, Any], service: dict[str, Any]) -> list[dict[str, Any]]:
    """Evaluate real completion facts. All awards share source BOOKING:<id>, so
    calling this twice (e.g. retried request) produces no duplicates.
    """
    awarded: list[dict[str, Any]] = []
    child_id = booking["childId"]
    source_id = booking["id"]

    prior = conn.execute(
        'SELECT 1 FROM "sf_booking" WHERE "childId"=? AND "status"=\'COMPLETED\' '
        'AND "id"<>? LIMIT 1',
        (child_id, source_id),
    ).fetchone()
    if not prior:
        star = award_star(conn, child_id, "FIRST_COURSE", "BOOKING", source_id)
        if star:
            awarded.append(star)

    sport = f"{service.get('sportType', '')}{service.get('title', '')}"
    if "平衡" in sport or "协调" in sport:
        star = award_star(conn, child_id, "BALANCE", "BOOKING", source_id, "STAR_BALANCE")
        if star:
            awarded.append(star)
    if "篮球" in sport:
        star = award_star(conn, child_id, "BASKETBALL", "BOOKING", source_id, "STAR_BASKETBALL")
        if star:
            awarded.append(star)
    if not awarded and not conn.execute(
        'SELECT 1 FROM "sf_growth_star" WHERE "childId"=? AND "sourceType"=\'BOOKING\' AND "sourceId"=? LIMIT 1',
        (child_id, source_id),
    ).fetchone():
        star = award_star(conn, child_id, "COURSE_COMPLETED", "BOOKING", source_id)
        if star:
            awarded.append(star)
    return awarded


def stars_for_child(conn: Any, child_id: str, viewer_id: str | None = None) -> dict[str, Any]:
    """Render-ready star map payload for GET /api/children/{id}/stars."""
    rows = conn.execute(
        'SELECT s.*, seen."seenAt", b."coachId", tr."id" AS "recordId", tr."durationMinutes", '
        'r."durationSeconds" FROM "sf_growth_star" s '
        'LEFT JOIN "sf_growth_star_seen" seen ON seen."starId"=s."id" AND seen."userId"=? '
        'LEFT JOIN "sf_booking" b ON s."sourceType"=\'BOOKING\' AND b."id"=s."sourceId" '
        'LEFT JOIN "sf_training_record" tr ON tr."id"=('
        'SELECT t."id" FROM "sf_training_record" t WHERE t."bookingId"=b."id" '
        'ORDER BY t."createdAt" DESC,t."id" DESC LIMIT 1) '
        'LEFT JOIN "sf_training_result" r ON s."sourceType"=\'TRAINING_RESULT\' AND r."id"=s."sourceId" '
        'WHERE s."childId"=? ORDER BY s."earnedAt",s."id"',
        (viewer_id, child_id),
    ).fetchall()
    stars: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    constellations: dict[str, int] = {}
    for index, row in enumerate(rows):
        base = STAR_DEFS.get(row["starType"], {})
        try:
            extra = json.loads(row["metadataJson"] or "{}")
        except json.JSONDecodeError:
            extra = {}
        metadata = {
            "color": extra.get("color", base.get("color", "#FFD166")),
            "constellation": extra.get("constellation", base.get("constellation", "启程座")),
            "stage": extra.get("stage", base.get("stage", "起步")),
            "animation": extra.get("animation", base.get("animation", "ignite")),
            "position": _position(index),
        }
        constellations[metadata["constellation"]] = constellations.get(metadata["constellation"], 0) + 1
        earned_at = db.ms_to_iso(row["earnedAt"])
        record_id = row["recordId"] or (row["sourceId"] if row["sourceType"] == "TRAINING_RESULT" else None)
        stars.append(
            {
                "starId": row["id"],
                "childId": child_id,
                "starType": row["starType"],
                "title": row["title"],
                "description": row["description"],
                "sourceType": row["sourceType"],
                "sourceId": row["sourceId"],
                "coachId": row["coachId"],
                "recordId": record_id,
                "durationMinutes": row["durationMinutes"],
                "durationSeconds": row["durationSeconds"],
                "earnedAt": earned_at,
                "metadata": metadata,
            }
        )
        if viewer_id and row["seenAt"] is None:
            events.append({
                "eventId": row["id"],
                "nodeId": row["id"],
                "childId": child_id,
                "recordId": record_id or row["sourceId"],
                "type": "growth.star_earned",
                "occurredAt": earned_at,
            })
    return {
        "childId": child_id,
        "total": len(stars),
        "disclaimer": DISCLAIMER,
        "constellations": [
            {"name": name, "count": count} for name, count in sorted(constellations.items())
        ],
        "stars": stars,
        "events": events,
    }
