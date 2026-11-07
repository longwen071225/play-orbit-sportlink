"""Authentication, role control and child-data isolation for StarFit.

Tokens are HMAC-signed and stateless; the secret is server-side only.
Password storage uses PBKDF2-HMAC-SHA256 from the standard library, so no new
dependency is required. Child data is NEVER readable by child_id alone.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Callable

from fastapi import Depends, Request

from .. import db
from ..agent import ApiError
from ..config import settings

TOKEN_TTL_SECONDS = 7 * 24 * 3600
PBKDF2_ROUNDS = 120_000


def _secret() -> str:
    return (
        getattr(settings, "STARFIT_SECRET", "")
        or os.environ.get("SOLOPILOT_STARFIT_SECRET")
        or "starfit-dev-secret-change-me"
    )


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(rounds)
        ).hex()
        return hmac.compare_digest(calc, digest)
    except Exception:
        return False


def make_token(user_id: str, role: str) -> str:
    payload = {"uid": user_id, "role": role, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).decode("ascii").rstrip("=")
    sig = hmac.new(_secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def parse_token(token: str) -> dict[str, Any] | None:
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(
            _secret().encode("utf-8"), body.encode("ascii"), hashlib.sha256
        ).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            return None
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def get_current_user(request: Request) -> dict[str, Any]:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHORIZED", "缺少 Bearer Token，请先调用 /api/auth/login")
    payload = parse_token(header[7:].strip())
    if not payload:
        raise ApiError(401, "INVALID_TOKEN", "Token 无效或已过期")
    with db.get_conn() as conn:
        row = conn.execute('SELECT * FROM "sf_user" WHERE "id" = ?', (payload.get("uid"),)).fetchone()
    if not row or row["status"] != "ACTIVE":
        raise ApiError(401, "USER_INACTIVE", "用户不存在或已停用")
    return {"id": row["id"], "phone": row["phone"], "name": row["name"], "role": row["role"]}


def require_roles(*roles: str) -> Callable:
    def _dep(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user["role"] not in roles:
            raise ApiError(403, "FORBIDDEN", f"该接口仅允许 {'/'.join(roles)} 角色访问")
        return user

    return _dep


def assert_child_access(conn: Any, user: dict[str, Any], child_id: str) -> dict[str, Any]:
    """Authorize a child profile. PARENT needs a guardianship link; COACH needs
    an accepted/in-progress/completed booking for their own coach profile.
    ADMIN may read for moderation. A bare child_id is never sufficient.
    """
    row = conn.execute('SELECT * FROM "sf_child" WHERE "id" = ?', (child_id,)).fetchone()
    if not row:
        raise ApiError(404, "CHILD_NOT_FOUND", f"儿童档案 {child_id} 不存在")

    role = user["role"]
    if role == "ADMIN":
        return dict(row)

    if role == "PARENT":
        linked = conn.execute(
            'SELECT 1 FROM "sf_guardian_relationship" WHERE "childId" = ? AND "userId" = ?',
            (child_id, user["id"]),
        ).fetchone()
        if linked or row["guardianId"] == user["id"]:
            return dict(row)
        raise ApiError(403, "CHILD_ACCESS_DENIED", "只能访问自己有监护权限的儿童档案")

    if role == "COACH":
        coach = conn.execute('SELECT "id" FROM "sf_coach" WHERE "userId" = ?', (user["id"],)).fetchone()
        if coach:
            linked = conn.execute(
                'SELECT 1 FROM "sf_booking" WHERE "childId" = ? AND "coachId" = ? '
                "AND \"status\" IN ('ACCEPTED','IN_PROGRESS','COMPLETED') LIMIT 1",
                (child_id, coach["id"]),
            ).fetchone()
            if linked:
                return dict(row)
        raise ApiError(403, "CHILD_ACCESS_DENIED", "教练只能访问与自己已授权课程相关的儿童训练信息")

    raise ApiError(403, "CHILD_ACCESS_DENIED", "无权访问该儿童档案")


def coach_id_for_user(conn: Any, user: dict[str, Any]) -> str:
    if user["role"] != "COACH":
        raise ApiError(403, "FORBIDDEN", "仅教练可执行该操作")
    row = conn.execute('SELECT "id" FROM "sf_coach" WHERE "userId" = ?', (user["id"],)).fetchone()
    if not row:
        raise ApiError(403, "COACH_PROFILE_MISSING", "当前账号未绑定教练资料")
    return row["id"]
