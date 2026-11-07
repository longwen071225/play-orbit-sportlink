"""StarFit incremental schema for the shared SQLite database.

Non-destructive by construction: create missing tables and add missing columns.
The legacy Prisma tables ("Lead", "Booking", "TrainingPlan", ...) are NEVER
touched -- they are owned by prisma/schema.prisma and the Node/Fastify service,
so altering them would break the existing API. The sf_ prefix keeps the new
platform tables unambiguous while living in the same prisma/dev.db file.
"""
from __future__ import annotations

from typing import Any

from .. import db

DDL = """
CREATE TABLE IF NOT EXISTS "sf_user" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "phone" TEXT NOT NULL UNIQUE,
    "name" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "role" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',
    "createdAt" INTEGER NOT NULL,
    "updatedAt" INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS "sf_child" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "guardianId" TEXT NOT NULL,
    "nickname" TEXT NOT NULL,
    "age" INTEGER NOT NULL,
    "sportsInterests" TEXT NOT NULL DEFAULT '[]',
    "trainingGoals" TEXT NOT NULL DEFAULT '[]',
    "createdAt" INTEGER NOT NULL,
    "updatedAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_child_guardian_idx" ON "sf_child"("guardianId");

CREATE TABLE IF NOT EXISTS "sf_guardian_relationship" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "childId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "relationship" TEXT NOT NULL DEFAULT 'GUARDIAN',
    "createdAt" INTEGER NOT NULL,
    UNIQUE ("childId", "userId")
);
CREATE INDEX IF NOT EXISTS "sf_guardian_user_idx" ON "sf_guardian_relationship"("userId");

CREATE TABLE IF NOT EXISTS "sf_coach" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" TEXT,
    "name" TEXT NOT NULL,
    "serviceAreas" TEXT NOT NULL DEFAULT '[]',
    "courseTypes" TEXT NOT NULL DEFAULT '[]',
    "priceCents" INTEGER NOT NULL,
    "bio" TEXT NOT NULL DEFAULT '',
    "certificateStatus" TEXT NOT NULL DEFAULT 'PENDING',
    "avatarUrl" TEXT NOT NULL DEFAULT '',
    "createdAt" INTEGER NOT NULL,
    "updatedAt" INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS "sf_service" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "coachId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "sportType" TEXT NOT NULL,
    "ageMin" INTEGER NOT NULL DEFAULT 5,
    "ageMax" INTEGER NOT NULL DEFAULT 12,
    "priceCents" INTEGER NOT NULL,
    "durationMinutes" INTEGER NOT NULL DEFAULT 60,
    "description" TEXT NOT NULL DEFAULT '',
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',
    "createdAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_service_coach_idx" ON "sf_service"("coachId");

CREATE TABLE IF NOT EXISTS "sf_coach_availability" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "coachId" TEXT NOT NULL,
    "startAt" INTEGER NOT NULL,
    "endAt" INTEGER NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'OPEN',
    "createdAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_availability_coach_idx" ON "sf_coach_availability"("coachId", "startAt");

CREATE TABLE IF NOT EXISTS "sf_booking" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "parentId" TEXT NOT NULL,
    "childId" TEXT NOT NULL,
    "coachId" TEXT NOT NULL,
    "serviceId" TEXT NOT NULL,
    "startAt" INTEGER NOT NULL,
    "endAt" INTEGER NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'PENDING',
    "paymentStatus" TEXT NOT NULL DEFAULT 'SIMULATED_UNPAID',
    "amountCents" INTEGER NOT NULL,
    "note" TEXT NOT NULL DEFAULT '',
    "createdAt" INTEGER NOT NULL,
    "updatedAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_booking_parent_idx" ON "sf_booking"("parentId");
CREATE INDEX IF NOT EXISTS "sf_booking_coach_time_idx" ON "sf_booking"("coachId", "startAt", "endAt");
CREATE INDEX IF NOT EXISTS "sf_booking_child_idx" ON "sf_booking"("childId");

CREATE TABLE IF NOT EXISTS "sf_training_record" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "bookingId" TEXT NOT NULL,
    "childId" TEXT NOT NULL,
    "coachId" TEXT NOT NULL,
    "durationMinutes" INTEGER NOT NULL,
    "content" TEXT NOT NULL,
    "performance" TEXT NOT NULL DEFAULT '{}',
    "createdAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_training_record_child_idx" ON "sf_training_record"("childId", "createdAt");
CREATE INDEX IF NOT EXISTS "sf_training_record_booking_idx" ON "sf_training_record"("bookingId", "createdAt", "id");

CREATE TABLE IF NOT EXISTS "sf_exercise" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "minAge" INTEGER NOT NULL,
    "maxAge" INTEGER NOT NULL,
    "difficulty" TEXT NOT NULL,
    "trainingGoal" TEXT NOT NULL,
    "instructions" TEXT NOT NULL DEFAULT '[]',
    "commonMistakes" TEXT NOT NULL DEFAULT '[]',
    "equipment" TEXT NOT NULL DEFAULT '[]',
    "safetyNotes" TEXT NOT NULL DEFAULT '',
    "videoUrl" TEXT NOT NULL DEFAULT '',
    "model3dUrl" TEXT NOT NULL DEFAULT '',
    "tags" TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS "sf_exercise_category_idx" ON "sf_exercise"("category");

CREATE TABLE IF NOT EXISTS "sf_training_plan" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "childId" TEXT NOT NULL,
    "coachId" TEXT,
    "agentSessionId" TEXT,
    "title" TEXT NOT NULL,
    "planJson" TEXT NOT NULL,
    "disclaimer" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'DRAFT',
    "createdAt" INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS "sf_family_task" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "childId" TEXT NOT NULL,
    "bookingId" TEXT,
    "coachId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "itemsJson" TEXT NOT NULL DEFAULT '[]',
    "goalCount" INTEGER NOT NULL DEFAULT 1,
    "status" TEXT NOT NULL DEFAULT 'OPEN',
    "createdAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_family_task_child_idx" ON "sf_family_task"("childId");

CREATE TABLE IF NOT EXISTS "sf_task_submission" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "taskId" TEXT NOT NULL,
    "parentId" TEXT NOT NULL,
    "content" TEXT NOT NULL DEFAULT '',
    "photoUrls" TEXT NOT NULL DEFAULT '[]',
    "status" TEXT NOT NULL DEFAULT 'SUBMITTED',
    "coachFeedback" TEXT NOT NULL DEFAULT '',
    "createdAt" INTEGER NOT NULL,
    "reviewedAt" INTEGER
);
CREATE INDEX IF NOT EXISTS "sf_task_submission_task_idx" ON "sf_task_submission"("taskId");

-- Idempotent rewards: one (child, event, source) can never be rewarded twice.
CREATE TABLE IF NOT EXISTS "sf_reward_event" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "childId" TEXT NOT NULL,
    "eventType" TEXT NOT NULL,
    "sourceType" TEXT NOT NULL,
    "sourceId" TEXT NOT NULL,
    "starsAwarded" INTEGER NOT NULL DEFAULT 0,
    "createdAt" INTEGER NOT NULL,
    UNIQUE ("childId", "eventType", "sourceType", "sourceId")
);

CREATE TABLE IF NOT EXISTS "sf_growth_star" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "childId" TEXT NOT NULL,
    "starType" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT NOT NULL DEFAULT '',
    "sourceType" TEXT NOT NULL,
    "sourceId" TEXT NOT NULL,
    "earnedAt" INTEGER NOT NULL,
    "metadataJson" TEXT NOT NULL DEFAULT '{}',
    UNIQUE ("childId", "starType", "sourceType", "sourceId")
);
CREATE INDEX IF NOT EXISTS "sf_growth_star_child_idx" ON "sf_growth_star"("childId", "earnedAt");

CREATE TABLE IF NOT EXISTS "sf_growth_star_seen" (
    "starId" TEXT NOT NULL REFERENCES "sf_growth_star"("id") ON DELETE CASCADE,
    "userId" TEXT NOT NULL REFERENCES "sf_user"("id") ON DELETE CASCADE,
    "seenAt" INTEGER NOT NULL,
    PRIMARY KEY ("starId", "userId")
);

CREATE TABLE IF NOT EXISTS "sf_video" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "title" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "exerciseId" TEXT,
    "ageMin" INTEGER NOT NULL DEFAULT 5,
    "ageMax" INTEGER NOT NULL DEFAULT 12,
    "videoUrl" TEXT NOT NULL DEFAULT '',
    "thumbnailUrl" TEXT NOT NULL DEFAULT '',
    "durationSeconds" INTEGER NOT NULL DEFAULT 0,
    "createdAt" INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS "sf_agent_session" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" TEXT NOT NULL,
    "childId" TEXT,
    "title" TEXT NOT NULL DEFAULT '',
    "stateJson" TEXT NOT NULL DEFAULT '{}',
    "createdAt" INTEGER NOT NULL,
    "updatedAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_agent_session_user_idx" ON "sf_agent_session"("userId");

CREATE TABLE IF NOT EXISTS "sf_agent_message" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "sessionId" TEXT NOT NULL,
    "role" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "toolCallsJson" TEXT,
    "toolResultsJson" TEXT,
    "createdAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_agent_message_session_idx" ON "sf_agent_message"("sessionId", "createdAt");

-- Motion Coach (SportLink MVP 1.1): one supervised training run of a child.
CREATE TABLE IF NOT EXISTS "sf_training_session" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "childId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "taskId" TEXT,
    "exerciseId" TEXT NOT NULL,
    "mode" TEXT NOT NULL DEFAULT 'POSE',
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',
    "targetReps" INTEGER NOT NULL DEFAULT 0,
    "targetSeconds" INTEGER NOT NULL DEFAULT 0,
    "repCount" INTEGER NOT NULL DEFAULT 0,
    "validRepCount" INTEGER NOT NULL DEFAULT 0,
    "holdMs" INTEGER NOT NULL DEFAULT 0,
    "eventCount" INTEGER NOT NULL DEFAULT 0,
    "errorCountsJson" TEXT NOT NULL DEFAULT '{}',
    "avgConfidence" REAL NOT NULL DEFAULT 0,
    "poseLostCount" INTEGER NOT NULL DEFAULT 0,
    "startedAt" INTEGER NOT NULL,
    "endedAt" INTEGER,
    "updatedAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_training_session_child_idx" ON "sf_training_session"("childId", "startedAt");
CREATE INDEX IF NOT EXISTS "sf_training_session_user_idx" ON "sf_training_session"("userId", "startedAt");

-- Structured facts produced by the local pose engine. Raw keypoints/video are
-- NEVER uploaded or stored by design.
CREATE TABLE IF NOT EXISTS "sf_pose_feedback_event" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "sessionId" TEXT NOT NULL,
    "childId" TEXT NOT NULL,
    "exerciseId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "code" TEXT NOT NULL DEFAULT '',
    "confidence" REAL,
    "metricsJson" TEXT NOT NULL DEFAULT '{}',
    "clientMs" INTEGER,
    "createdAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_pose_event_session_idx" ON "sf_pose_feedback_event"("sessionId", "createdAt");

-- One result per session (UNIQUE) -> repeating POST complete is idempotent and
-- can never mint a second growth star (stars.py adds its own unique guards).
CREATE TABLE IF NOT EXISTS "sf_training_result" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "sessionId" TEXT NOT NULL UNIQUE,
    "childId" TEXT NOT NULL,
    "exerciseId" TEXT NOT NULL,
    "taskId" TEXT,
    "durationSeconds" INTEGER NOT NULL DEFAULT 0,
    "repCount" INTEGER NOT NULL DEFAULT 0,
    "validRepCount" INTEGER NOT NULL DEFAULT 0,
    "holdMs" INTEGER NOT NULL DEFAULT 0,
    "errorCountsJson" TEXT NOT NULL DEFAULT '{}',
    "avgConfidence" REAL NOT NULL DEFAULT 0,
    "completed" INTEGER NOT NULL DEFAULT 0,
    "starAwarded" INTEGER NOT NULL DEFAULT 0,
    "summary" TEXT NOT NULL DEFAULT '',
    "createdAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_training_result_child_idx" ON "sf_training_result"("childId", "createdAt");

CREATE TABLE IF NOT EXISTS "sf_portal_audit" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "entityType" TEXT NOT NULL,
    "entityId" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "actorId" TEXT NOT NULL,
    "actorName" TEXT NOT NULL,
    "reason" TEXT NOT NULL DEFAULT '',
    "createdAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_portal_audit_entity_idx" ON "sf_portal_audit"("entityType","entityId","createdAt");
CREATE TABLE IF NOT EXISTS "sf_portal_dispute" (
    "bookingId" TEXT NOT NULL PRIMARY KEY,
    "status" TEXT NOT NULL,
    "reason" TEXT NOT NULL,
    "resolution" TEXT NOT NULL DEFAULT '',
    "createdAt" INTEGER NOT NULL,
    "updatedAt" INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS "sf_portal_photo" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "bookingId" TEXT NOT NULL,
    "childId" TEXT NOT NULL,
    "coachId" TEXT NOT NULL,
    "filename" TEXT NOT NULL,
    "mimeType" TEXT NOT NULL,
    "content" BLOB NOT NULL,
    "createdAt" INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS "sf_portal_photo_child_idx" ON "sf_portal_photo"("childId");
"""

STARFIT_TABLES = [
    "sf_user",
    "sf_child",
    "sf_guardian_relationship",
    "sf_coach",
    "sf_service",
    "sf_coach_availability",
    "sf_booking",
    "sf_training_record",
    "sf_exercise",
    "sf_training_plan",
    "sf_family_task",
    "sf_task_submission",
    "sf_reward_event",
    "sf_growth_star",
    "sf_growth_star_seen",
    "sf_video",
    "sf_agent_session",
    "sf_agent_message",
    "sf_training_session",
    "sf_pose_feedback_event",
    "sf_training_result",
    "sf_portal_audit",
    "sf_portal_dispute",
    "sf_portal_photo",
]


def ensure_schema() -> None:
    """Create missing StarFit tables only. Safe to call on every startup."""
    with db.get_conn() as conn:
        conn.executescript(DDL)
        _add_agent_kind(conn)
        _add_portal_columns(conn)


def _add_agent_kind(conn: Any) -> None:
    """Non-destructive migration: distinguish Booking vs Motion Coach sessions."""
    cols = {r["name"] for r in conn.execute('PRAGMA table_info("sf_agent_session")').fetchall()}
    if "agentKind" not in cols:
        conn.execute('ALTER TABLE "sf_agent_session" ADD COLUMN "agentKind" TEXT NOT NULL DEFAULT \'BOOKING\'')


def _add_portal_columns(conn: Any) -> None:
    """Add only missing columns; never rewrite or reset existing business data."""
    additions = {
        "sf_booking": {"address": "TEXT NOT NULL DEFAULT ''"},
        "sf_child": {
            "photoConsent": "INTEGER NOT NULL DEFAULT 0",
            "photoConsentBy": "TEXT NOT NULL DEFAULT ''",
            "photoConsentAt": "INTEGER",
        },
        "sf_coach": {"reviewReason": "TEXT NOT NULL DEFAULT ''"},
    }
    for table, fields in additions.items():
        columns = {row["name"] for row in conn.execute(f'PRAGMA table_info("{table}")')}
        for name, definition in fields.items():
            if name not in columns:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')


def clear_all() -> None:
    """Test helper: remove StarFit rows only (legacy tables are untouched)."""
    with db.get_conn() as conn:
        for table in reversed(STARFIT_TABLES):
            conn.execute(f'DELETE FROM "{table}"')
