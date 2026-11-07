"""SportLink Motion Coach Agent (StarFit module).

The SECOND agent beside the Booking Agent. Two modes:

Mode A (POSE, camera on): the frontend runs pose estimation locally and posts
structured events to /api/training/sessions/{id}/feedback. The rule engine
(pose.py) owns the facts; this module only explains them. The LLM is NEVER
shown raw keypoints and can never invent reps, errors or stars.

Mode B (GUIDED, no camera): a deterministic reminder state machine walks the
child through the coach-assigned family task (next exercise, sets, rest, tips,
encouragement). The LLM only words summaries when explicitly asked.

Hard invariants:
  * Independent system prompt and tool whitelist (read-only subset of the
    Booking Agent registry - no booking, no confirmation, no write tools).
  * Control phrases ("继续/下一组/做完了") are answered deterministically with
    ZERO model calls - the 23.6s multi-round latency never hits the training UX.
  * Bailian failure degrades to the deterministic templates (degraded=True),
    never to fabricated pose judgments.
"""
from __future__ import annotations

import json
import time
from typing import Any

from .. import db
from ..agent import ApiError
from ..config import settings
from ..llm import BailianClient, LLMError, TokenStats
from . import pose as pose_engine
from . import services
from .agent import SAFETY_NOTE, ToolContext, _save_message, execute_tool
from .auth import assert_child_access

MOTION_TOOL_NAMES = {"get_child_profile", "get_training_history", "search_exercises", "get_motion_session"}

MOTION_SYSTEM_PROMPT = f"""你是「星动到家 SportLink」的 AI 运动陪练教练，对象是 5-12 岁儿童和家长。

硬性规则：
1. 动作对不对、做了几次，只能依据规则引擎的真实事件（repCount、validRepCount、
   errorCounts、completionCheck）。你绝不编造次数、评分或"我看到了"之类的描述；
   没有数据时就说"我这边没有姿态数据"，并引导孩子打开摄像头训练。
2. 语气像身边的教练：简短、具体、鼓励为主，每次不超过 3 句话，适合直接读给孩子听。
3. 纠错只针对规则引擎给出的错误码和提示语，不要发明新的动作判断标准。
4. 遇到孩子说疼痛、头晕、不舒服：立即让他停止休息，并提醒联系家长或教练。
5. 训练目标来自教练布置的家庭任务或动作配置的完成标准，不要自行加量。
6. 安全底线：{SAFETY_NOTE}
"""

REST_SECONDS = 30
_CONTROL_WORDS_NEXT = ("继续", "下一", "接着", "开始吧", "开始训练", "准备好了")
_CONTROL_WORDS_DONE = ("做完了", "完成了", "练完了", "好了")
_CONTROL_WORDS_SUMMARY = ("总结", "表现", "怎么样", "结果")


# ------------------------------------------------------------------ guidance engine (Mode B)
def _tip_for_item(conn: Any, item: dict[str, Any]) -> str:
    """Deterministic coaching tip: motion config first, then the knowledge base."""
    exercise_id = str(item.get("exerciseId") or "")
    config = pose_engine.MOTION_CONFIGS.get(exercise_id)
    if config and config.get("tips"):
        return str(config["tips"][0])
    if exercise_id:
        row = conn.execute(
            'SELECT "commonMistakes","instructions" FROM "sf_exercise" WHERE "id"=?', (exercise_id,)
        ).fetchone()
        if row:
            mistakes = services._loads(row["commonMistakes"], [])
            if mistakes:
                return f"注意不要：{mistakes[0]}"
            steps = services._loads(row["instructions"], [])
            if steps:
                return str(steps[0])
    return str(item.get("tip") or "跟着节奏慢慢来，注意安全")


def _item_label(item: dict[str, Any]) -> str:
    name = str(item.get("name") or item.get("exerciseId") or "动作")
    reps, sets, seconds = item.get("reps"), item.get("sets"), item.get("seconds")
    detail = []
    if sets:
        detail.append(f"{sets} 组")
    if reps:
        detail.append(f"每组 {reps} 个")
    if seconds:
        detail.append(f"每组 {seconds} 秒")
    return f"{name}（{'，'.join(detail)}）" if detail else name


def _pick_task(conn: Any, user: dict[str, Any], child_id: str, task_id: str | None) -> dict[str, Any] | None:
    if task_id:
        row = conn.execute('SELECT * FROM "sf_family_task" WHERE "id"=?', (task_id,)).fetchone()
        if not row or row["childId"] != child_id:
            raise ApiError(404, "TASK_NOT_FOUND", f"家庭任务 {task_id} 不存在或不属于这个孩子")
        assert_child_access(conn, user, child_id)
        return services.task_out(row)
    rows = conn.execute(
        'SELECT * FROM "sf_family_task" WHERE "childId"=? AND "status" IN (\'OPEN\',\'SUBMITTED\') '
        'ORDER BY "createdAt" DESC LIMIT 1',
        (child_id,),
    ).fetchall()
    for row in rows:
        try:
            assert_child_access(conn, user, child_id)
        except ApiError:
            continue
        return services.task_out(row)
    return None


def _motion_state(state: dict[str, Any]) -> dict[str, Any]:
    return state.setdefault("motion", {"taskStep": 0, "restingUntilMs": 0})


def build_guidance(
    conn: Any,
    user: dict[str, Any],
    child_id: str,
    task_id: str | None,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic Mode B reminder: what should the child do RIGHT NOW."""
    task = _pick_task(conn, user, child_id, task_id)
    motion = _motion_state(state)
    step = int(motion.get("taskStep", 0) or 0)

    if not task or not task.get("items"):
        return {
            "task": None, "step": "FREE_PRACTICE",
            "text": "现在没有教练布置的家庭任务。可以先做开合跳或深蹲热热身，需要的时候让教练给你布置一个训练任务。",
            "voice": "现在没有教练布置的任务，可以先自由练习热热身。",
        }

    items = task["items"]
    if step >= len(items):
        return {
            "task": {"id": task["id"], "title": task["title"]},
            "step": "TASK_DONE",
            "text": f"「{task['title']}」的所有动作都练完啦，非常棒！让家长在任务里提交完成记录，教练确认后还能拿挑战星。",
            "voice": "所有动作都练完啦，真棒！让爸爸妈妈提交任务，还能拿挑战星哦。",
        }

    item = items[step] if isinstance(items[step], dict) else {"name": str(items[step])}
    label = _item_label(item)
    tip = _tip_for_item(conn, item)
    now = db.now_ms()
    resting = now < int(motion.get("restingUntilMs", 0) or 0)

    if resting:
        remain = max(1, (int(motion["restingUntilMs"]) - now) // 1000)
        return {
            "task": {"id": task["id"], "title": task["title"]},
            "step": "REST", "restSecondsLeft": remain,
            "text": f"休息一下，还剩 {remain} 秒。喝口水，然后我们做下一个动作。",
            "voice": f"休息一下，还剩{remain}秒，喝口水。",
        }

    prefix = f"家庭任务「{task['title']}」" if step == 0 else "下一个动作"
    return {
        "task": {"id": task["id"], "title": task["title"]},
        "step": "DO",
        "stepIndex": step,
        "text": f"{prefix}：{label}。{tip}做完告诉我「做完了」，我陪你休息一下再继续。",
        "voice": f"接下来做{label}。{tip}",
    }


def advance_guidance(state: dict[str, Any], total_items: int) -> None:
    motion = _motion_state(state)
    motion["taskStep"] = int(motion.get("taskStep", 0) or 0) + 1
    motion["restingUntilMs"] = db.now_ms() + REST_SECONDS * 1000 if motion["taskStep"] < max(total_items, 1) else 0


# ------------------------------------------------------------------ deterministic replies
def _deterministic_reply(
    conn: Any,
    user: dict[str, Any],
    child_id: str,
    state: dict[str, Any],
    message: str,
    task_id: str | None,
    training_session_id: str | None,
) -> dict[str, Any] | None:
    """Template answers that never touch the LLM. Returns None when the message
    should go to the model."""
    lowered = message.strip()

    if any(w in lowered for w in _CONTROL_WORDS_SUMMARY):
        return None  # summaries are worth a model call (wording), still fallback-safe

    if any(w in lowered for w in _CONTROL_WORDS_DONE):
        task = _pick_task(conn, user, child_id, task_id)
        if task and task.get("items"):
            advance_guidance(state, len(task["items"]))
        guidance = build_guidance(conn, user, child_id, task_id, state)
        session_note = ""
        if training_session_id:
            row = conn.execute(
                'SELECT "status" FROM "sf_training_session" WHERE "id"=?', (training_session_id,)
            ).fetchone()
            if row and row["status"] == "ACTIVE":
                session_note = "摄像头训练的话，点「完成训练」让系统记录成绩。"
        return {
            "reply": f"好样的！休息 {REST_SECONDS} 秒。" + str(guidance.get("text", "")) + session_note,
            "guidance": guidance,
        }

    if any(w in lowered for w in _CONTROL_WORDS_NEXT):
        # 「继续」= 孩子主动跳过组间休息
        _motion_state(state)["restingUntilMs"] = 0
        guidance = build_guidance(conn, user, child_id, task_id, state)
        return {"reply": str(guidance.get("text", "")), "guidance": guidance}

    if any(k in lowered for k in ("疼", "痛", "头晕", "不舒服", "受伤")):
        return {
            "reply": "马上停下来休息，别再勉强做动作。把这里告诉爸爸妈妈或教练；如果一直疼，要让大人带你去看医生。",
            "guidance": build_guidance(conn, user, child_id, task_id, state),
        }

    if any(k in lowered for k in ("你好", "在吗", "开始", "怎么玩", "怎么练")):
        guidance = build_guidance(conn, user, child_id, task_id, state)
        return {"reply": str(guidance.get("text", "")), "guidance": guidance}

    return None


def _fallback_summary_text(conn: Any, child_id: str) -> str:
    row = conn.execute(
        'SELECT * FROM "sf_training_result" WHERE "childId"=? ORDER BY "createdAt" DESC LIMIT 1',
        (child_id,),
    ).fetchone()
    if not row:
        return "还没有训练记录。打开摄像头完成一次训练，我就能陪你并记录成绩啦。"
    errors = services._loads(row["errorCountsJson"], {})
    worst = max(errors.items(), key=lambda kv: kv[1]) if errors else None
    exercise = conn.execute('SELECT "name" FROM "sf_exercise" WHERE "id"=?', (row["exerciseId"],)).fetchone()
    name = exercise["name"] if exercise else row["exerciseId"]
    if row["completed"]:
        detail = f"完成 {row['validRepCount']} 次有效动作" if row["validRepCount"] else f"保持 {round(row['holdMs'] / 1000.0)} 秒"
        extra = f"，最需要注意的：{worst[0]}" if worst else ""
        return f"{name}训练完成！{detail}，姿态数据平均置信度 {row['avgConfidence']:.2f}{extra}。已经为你点亮一颗陪练星！"
    return f"上次{name}训练还没达标，随时可以继续，我陪你再练一组。"


# ------------------------------------------------------------------ orchestration
def _resolve_motion_session(
    conn: Any, user: dict[str, Any], payload: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    session_id = payload.get("sessionId")
    if session_id:
        row = conn.execute(
            'SELECT * FROM "sf_agent_session" WHERE "id"=? AND "userId"=? AND "agentKind"=\'MOTION\'',
            (session_id, user["id"]),
        ).fetchone()
        if not row:
            raise ApiError(404, "SESSION_NOT_FOUND", f"陪练会话 {session_id} 不存在或不属于当前用户")
        return session_id, json.loads(row["stateJson"] or "{}")
    session_id = db.new_id("mc")
    now = db.now_ms()
    conn.execute(
        'INSERT INTO "sf_agent_session" '
        '("id","userId","childId","agentKind","title","stateJson","createdAt","updatedAt") '
        "VALUES (?,?,?,'MOTION',?,?,?,?)",
        (session_id, user["id"], payload.get("childId"),
         str(payload.get("message", ""))[:40] or "AI 运动陪练",
         json.dumps({}, ensure_ascii=False), now, now),
    )
    return session_id, {}


def _child_context(conn: Any, user: dict[str, Any], child_id: str, task_id: str | None, session_state: dict[str, Any]) -> str:
    child = conn.execute('SELECT * FROM "sf_child" WHERE "id"=?', (child_id,)).fetchone()
    task = _pick_task(conn, user, child_id, task_id)
    parts = [f"当前儿童:{child['nickname']}（{child['age']} 岁,id={child['id']}）" if child else "未指定儿童"]
    if task:
        items = "、".join(_item_label(i) if isinstance(i, dict) else str(i) for i in task.get("items", []))
        parts.append(f"教练布置的家庭任务「{task['title']}」:{items}(共 {task['goalCount']} 项)")
    else:
        parts.append("暂无教练布置的家庭任务")
    latest = conn.execute(
        'SELECT "id","status" FROM "sf_training_session" WHERE "childId"=? ORDER BY "startedAt" DESC LIMIT 1',
        (child_id,),
    ).fetchone()
    if latest:
        parts.append(f"最近训练会话 {latest['id']}({latest['status']})，可用 get_motion_session 读取真实计数")
    step = int((session_state.get("motion") or {}).get("taskStep", 0) or 0)
    parts.append(f"提醒进度:第 {step} 步")
    return "；".join(parts) + "。"


def run_motion_chat(llm: BailianClient, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "")).strip()
    if not message:
        raise ApiError(400, "VALIDATION_ERROR", "message 必填")
    child_id = str(payload.get("childId") or "")
    task_id = payload.get("taskId") or None
    training_session_id = payload.get("trainingSessionId") or None
    run_started = time.time()
    stats = TokenStats()

    with db.get_conn() as conn:
        if not child_id:
            child = conn.execute(
                'SELECT c."id" FROM "sf_child" c LEFT JOIN "sf_guardian_relationship" g ON g."childId"=c."id" '
                'WHERE c."guardianId"=? OR g."userId"=? ORDER BY c."createdAt" LIMIT 1',
                (user["id"], user["id"]),
            ).fetchone()
            if not child:
                raise ApiError(404, "NO_CHILD_ACCESS", "当前账号没有可用的儿童档案")
            child_id = child["id"]
        assert_child_access(conn, user, child_id)
        with db.transaction() as tconn:
            session_id, state = _resolve_motion_session(tconn, user, {**payload, "childId": child_id})
        _save_message(conn, session_id, "user", message)

        deterministic = _deterministic_reply(conn, user, child_id, state, message, task_id, training_session_id)
        if deterministic is None and llm.mode == "mock":
            # Offline mode: keep the whole training UX deterministic (no mock-LLM
            # tool loop, no booking tools ever reachable from the Motion Coach).
            guidance = build_guidance(conn, user, child_id, task_id, state)
            if any(w in message for w in _CONTROL_WORDS_SUMMARY):
                deterministic = {"reply": _fallback_summary_text(conn, child_id), "guidance": guidance}
            else:
                deterministic = {
                    "reply": str(guidance.get("text", "")) + " 有什么想跟教练说的也可以告诉我。",
                    "guidance": guidance,
                }

    if deterministic is not None:
        reply = deterministic["reply"]
        guidance = deterministic.get("guidance")
        degraded = False
        with db.transaction() as conn:
            _save_message(conn, session_id, "assistant", reply)
            conn.execute(
                'UPDATE "sf_agent_session" SET "stateJson"=?, "updatedAt"=?, "childId"=COALESCE(?, "childId") WHERE "id"=?',
                (json.dumps(state, ensure_ascii=False), db.now_ms(), child_id, session_id),
            )
        return {
            "sessionId": session_id,
            "agentKind": "MOTION",
            "reply": reply,
            "guidance": guidance,
            "deterministic": True,
            "degraded": False,
            "llmMode": llm.mode,
            "model": "rule-engine",
            "toolCalls": [],
            "tokenUsage": stats.as_dict(),
            "latencyMs": int((time.time() - run_started) * 1000),
            "childId": child_id,
            "disclaimer": SAFETY_NOTE,
        }

    # ---- LLM path (free chat / summaries) with independent prompt + tool subset
    tool_log: list[dict[str, Any]] = []
    rounds = 0
    reply = ""
    last_model = llm.primary_model
    degraded = False
    fast_model = (settings.FAST_MODEL or "").strip() or None

    with db.get_conn() as conn:
        context_hint = _child_context(conn, user, child_id, task_id, state)
        summary_hint = ""
        if training_session_id:
            summary_hint = f"本次训练会话 ID:{training_session_id}。"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": MOTION_SYSTEM_PROMPT},
        {"role": "system", "content": context_hint + summary_hint},
    ]
    with db.get_conn() as conn:
        history = conn.execute(
            'SELECT "role","content" FROM "sf_agent_message" WHERE "sessionId"=? ORDER BY "createdAt","id"',
            (session_id,),
        ).fetchall()
    for h in history:
        if h["role"] in ("user", "assistant") and h["content"]:
            messages.append({"role": h["role"], "content": h["content"]})

    try:
        while rounds < settings.MAX_TOOL_ROUNDS:
            response = agent_chat_once(llm, messages, child_id, user, session_id, state, fast_model)
            stats.add(response.usage, response.model)
            last_model = response.model
            if not response.tool_calls:
                reply = response.content or "我在这呢！准备好就跟我一起练。"
                break
            messages.append({"role": "assistant", "content": None, "tool_calls": response.tool_calls})
            tool_results: list[dict[str, Any]] = []
            for call in response.tool_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                try:
                    raw = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    raw = {}
                with db.transaction() as conn:
                    ctx = ToolContext(conn=conn, user=user, session_id=session_id, state=state)
                    result = execute_tool(name, raw, ctx)
                tool_results.append({"tool_call_id": call.get("id"), "name": name, "result": result})
                tool_log.append({"name": name, "arguments": raw, "status": result.get("status"), "result": result})
                messages.append(
                    {"role": "tool", "tool_call_id": call.get("id"),
                     "content": json.dumps(result, ensure_ascii=False, default=str)}
                )
            rounds += 1
            with db.transaction() as conn:
                _save_message(conn, session_id, "assistant", "", response.tool_calls, tool_results)
        if not reply:
            reply = "刚才数据有点多，我捋一下：跟着教练布置的任务练就好，做完跟我说「做完了」。"
    except LLMError:
        degraded = True
        with db.get_conn() as fb_conn:
            reply = _fallback_text(fb_conn, child_id)

    with db.transaction() as conn:
        _save_message(conn, session_id, "assistant", reply)
        conn.execute(
            'UPDATE "sf_agent_session" SET "stateJson"=?, "updatedAt"=?, "childId"=COALESCE(?, "childId") WHERE "id"=?',
            (json.dumps(state, ensure_ascii=False), db.now_ms(), child_id, session_id),
        )

    return {
        "sessionId": session_id,
        "agentKind": "MOTION",
        "reply": reply,
        "guidance": None,
        "deterministic": False,
        "degraded": degraded,
        "llmMode": llm.mode,
        "model": last_model,
        "toolRounds": rounds,
        "toolCalls": tool_log,
        "tokenUsage": stats.as_dict(),
        "latencyMs": int((time.time() - run_started) * 1000),
        "childId": child_id,
        "disclaimer": SAFETY_NOTE,
    }


def _fallback_text(conn: Any, child_id: str) -> str:
    """Rule-based reply when Bailian is unreachable. Facts only, no invention."""
    return _fallback_summary_text(conn, child_id)


def agent_chat_once(
    llm: BailianClient,
    messages: list[dict[str, Any]],
    child_id: str,
    user: dict[str, Any],
    session_id: str,
    state: dict[str, Any],
    fast_model: str | None,
):
    from .agent import _chat as agent_loop_chat

    context = {"childId": child_id, "message": messages[-1]["content"] if messages else "",
               "agentKind": "MOTION", "user": user["id"], "sessionIdRef": session_id, "state": state}
    return agent_loop_chat(llm, messages, context, allowed_tools=MOTION_TOOL_NAMES, model_override=fast_model)
