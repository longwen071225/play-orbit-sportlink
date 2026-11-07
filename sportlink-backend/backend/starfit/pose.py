"""Motion rule engine for the SportLink Motion Coach (StarFit module).

Architecture (LLM never judges movement):
    camera -> local pose estimation (frontend, MediaPipe) -> keypoints
    -> rule engine (THIS config, shipped verbatim to the frontend)
    -> structured facts/events -> Motion Coach LLM only words them.

The server never receives video or raw keypoint streams: the frontend runs the
same config locally and posts only structured events (REP / HOLD / FORM_ERROR /
POSE_LOST / QUALITY_LOW). The server validates every event against this config,
keeps counters, and decides completion - the frontend cannot mint a completed
training or a growth star.

Every threshold below is a demo tuning value for healthy children aged 5-12 in
a supervised home setting. It is NOT a medically validated diagnostic standard.
"""
from __future__ import annotations

from typing import Any

ENGINE_NOTE = "所有角度/时长阈值均为训练演示用调参值，不构成医学或诊断标准。"

# Event types a pose frontend may post. Anything else is rejected.
EVENT_TYPES = {"REP", "HOLD", "FORM_ERROR", "POSE_LOST", "QUALITY_LOW"}

# Normalized joint names the frontend must provide (MediaPipe 33-landmark model,
# mapped by the demo page). Server never computes angles itself.
KNOWN_METRICS: dict[str, str] = {
    "kneeAngle": "膝关节角度（髋-膝-踝，度）",
    "trunkLeanAngle": "躯干前倾角（肩-髋-膝，度）",
    "supportKneeAngle": "支撑腿膝关节角度（度）",
    "armsOpen": "双臂是否过头（布尔）",
    "legsApart": "双脚开合是否大于肩宽（布尔）",
    "isOpen": "开合跳展开状态（布尔）",
    "isHolding": "单脚站立保持状态（布尔）",
    "hipShift": "髋部水平晃动幅度（相对肩宽）",
    "minKneeAngleInRep": "单次动作内最小膝关节角度（度）",
    "repDurationMs": "单次动作耗时（毫秒）",
}


def _reps_config(
    exercise_id: str,
    name: str,
    target_reps: int,
    rep_rule: dict[str, Any],
    error_rules: list[dict[str, Any]],
    tips: list[str],
) -> dict[str, Any]:
    return {
        "exerciseId": exercise_id,
        "name": name,
        "kind": "REPS",
        "targetReps": target_reps,
        "maxReps": 200,
        "minConfidence": 0.6,
        "repRule": rep_rule,
        "errorRules": error_rules,
        "tips": tips,
        "voiceCooldownSeconds": 4,
        "completion": {"type": "REPS", "reps": target_reps},
        "note": ENGINE_NOTE,
    }


def _hold_config(
    exercise_id: str,
    name: str,
    target_seconds: int,
    error_rules: list[dict[str, Any]],
    tips: list[str],
) -> dict[str, Any]:
    return {
        "exerciseId": exercise_id,
        "name": name,
        "kind": "HOLD",
        "targetSeconds": target_seconds,
        "minConfidence": 0.55,
        "holdRule": {"type": "BOOLEAN", "metric": "isHolding"},
        "errorRules": error_rules,
        "tips": tips,
        "voiceCooldownSeconds": 6,
        "completion": {"type": "HOLD", "seconds": target_seconds},
        "note": ENGINE_NOTE,
    }


MOTION_CONFIGS: dict[str, dict[str, Any]] = {
    # 自重深蹲：hip-knee-ankle 角度滞回判定一次完整蹲起
    "ex_str_01": _reps_config(
        "ex_str_01", "自重深蹲", 8,
        {"type": "ANGLE_HYSTERESIS", "metric": "kneeAngle", "enterBelow": 110.0, "exitAbove": 155.0},
        [
            {"code": "SQUAT_SHALLOW", "scope": "rep", "severity": "info",
             "check": {"metric": "minKneeAngleInRep", "op": "above", "value": 120.0},
             "message": "再蹲低一点，大腿大概与地面平行就很好"},
            {"code": "SQUAT_FAST", "scope": "rep", "severity": "info",
             "check": {"metric": "repDurationMs", "op": "below", "value": 1200},
             "message": "节奏放慢一点，下蹲两秒、起身一秒"},
            {"code": "TRUNK_LEAN", "scope": "frame", "severity": "warn",
             "check": {"metric": "trunkLeanAngle", "op": "above", "value": 60.0},
             "message": "上半身挺直，不要弯腰太多"},
        ],
        ["双脚与肩同宽，脚尖微微朝外", "下蹲时膝盖对准脚尖方向", "起身时收紧小肚子"],
    ),
    # 开合跳：双臂过头 + 双脚开过肩宽 = 展开，收回复位计一次
    "ex_coo_01": _reps_config(
        "ex_coo_01", "开合跳", 10,
        {"type": "BOOLEAN", "metric": "isOpen"},
        [
            {"code": "KNEE_STIFF", "scope": "rep", "severity": "info",
             "check": {"metric": "minKneeAngleInRep", "op": "above", "value": 150.0},
             "message": "落地时膝盖微微弯曲缓冲，轻一点"},
            {"code": "ARMS_LOW", "scope": "frame", "severity": "info",
             "check": {"metric": "armsOpen", "op": "below", "value": 1},
             "message": "跳开时双手在头顶击掌，举高一点"},
        ],
        ["落地轻一点，用脚掌缓冲", "保持小节奏，不用跳很高"],
    ),
    # 单脚站立：计时累计保持时长
    "ex_bal_01": _hold_config(
        "ex_bal_01", "单脚站立", 20,
        [
            {"code": "SUPPORT_BENT", "scope": "frame", "severity": "info",
             "check": {"metric": "supportKneeAngle", "op": "below", "value": 140.0},
             "message": "支撑腿伸直一点，稳稳站着"},
            {"code": "WOBBLING", "scope": "frame", "severity": "warn",
             "check": {"metric": "hipShift", "op": "above", "value": 0.15},
             "message": "收紧小肚子，眼睛看前方固定点"},
        ],
        ["双手侧平举帮助平衡", "眼睛看前方一个不动的东西", "旁边最好有大人在"],
    ),
}


def get_motion_config(exercise_id: str) -> dict[str, Any] | None:
    return MOTION_CONFIGS.get(exercise_id)


def error_codes(config: dict[str, Any]) -> set[str]:
    return {r["code"] for r in config.get("errorRules", [])}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _check_rule(check: dict[str, Any], metrics: dict[str, Any]) -> bool:
    """True when the rule is VIOLATED (metrics fail the expected condition)."""
    value = metrics.get(check.get("metric") or "")
    if value is None:
        return False
    op = check.get("op")
    threshold = check.get("value")
    try:
        if op == "above":
            return float(value) > float(threshold)
        if op == "below":
            return float(value) < float(threshold)
    except (TypeError, ValueError):
        return False
    return False


def apply_events(
    config: dict[str, Any],
    counters: dict[str, Any],
    events: list[dict[str, Any]],
    now_ms: int,
) -> dict[str, Any]:
    """Validate a batch of frontend events against the motion config.

    Pure function: returns new counters plus per-event verdicts. The server
    decides truth - a low-confidence or unknown event never mutates counters.
    """
    valid_codes = error_codes(config)
    min_conf = float(config.get("minConfidence", 0.5))
    max_reps = int(config.get("maxReps", 200))

    new = dict(counters)
    rep_count = int(new.get("repCount", 0) or 0)
    valid_reps = int(new.get("validRepCount", 0) or 0)
    hold_ms = int(new.get("holdMs", 0) or 0)
    event_count = int(new.get("eventCount", 0) or 0)
    conf_sum = float(new.get("confidenceSum", 0.0) or 0.0)
    conf_n = int(new.get("confidenceN", 0) or 0)
    errors: dict[str, int] = dict(new.get("errorCounts", {}) or {})
    last_code_ts: dict[str, int] = dict(new.get("lastErrorTs", {}) or {})
    pose_lost = int(new.get("poseLostCount", 0) or 0)

    verdicts: list[dict[str, Any]] = []
    accepted = 0
    for raw in events[:100]:  # hard cap per request
        if not isinstance(raw, dict):
            verdicts.append({"ok": False, "reason": "EVENT_NOT_OBJECT"})
            continue
        etype = str(raw.get("type") or "").upper()
        if etype not in EVENT_TYPES:
            verdicts.append({"ok": False, "reason": "EVENT_TYPE_UNKNOWN", "type": etype})
            continue

        confidence = raw.get("confidence")
        try:
            confidence = _clamp(float(confidence), 0.0, 1.0) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None

        event_out: dict[str, Any] = {"type": etype}

        if etype == "REP":
            if confidence is not None:
                conf_sum += confidence
                conf_n += 1
            if confidence is not None and confidence < min_conf:
                verdicts.append({**event_out, "ok": False, "reason": "LOW_CONFIDENCE"})
                continue
            if rep_count >= max_reps:
                verdicts.append({**event_out, "ok": False, "reason": "REP_LIMIT_REACHED"})
                continue
            rep_count += 1
            valid_reps += 1
            event_out.update({"repCount": rep_count, "counted": True})
            verdicts.append({**event_out, "ok": True})

        elif etype == "HOLD":
            try:
                delta = _clamp(float(raw.get("holdMs") or 0), 0.0, 60_000.0)
            except (TypeError, ValueError):
                verdicts.append({**event_out, "ok": False, "reason": "INVALID_HOLD_MS"})
                continue
            if confidence is not None:
                conf_sum += confidence
                conf_n += 1
                if confidence < min_conf:
                    verdicts.append({**event_out, "ok": False, "reason": "LOW_CONFIDENCE"})
                    continue
            if hold_ms >= 3_600_000:
                verdicts.append({**event_out, "ok": False, "reason": "HOLD_LIMIT_REACHED"})
                continue
            hold_ms += int(delta)
            event_out.update({"holdMs": int(delta), "holdMsTotal": hold_ms, "counted": True})
            verdicts.append({**event_out, "ok": True})

        elif etype == "FORM_ERROR":
            code = str(raw.get("code") or "")
            if code not in valid_codes:
                verdicts.append({**event_out, "ok": False, "reason": "ERROR_CODE_UNKNOWN", "code": code})
                continue
            # 去重：同一错误码 2 秒内的重复提示只记一次
            if now_ms - int(last_code_ts.get(code, 0)) < 2000:
                verdicts.append({**event_out, "ok": False, "reason": "DUPLICATE_SUPPRESSED", "code": code})
                continue
            last_code_ts[code] = now_ms
            errors[code] = errors.get(code, 0) + 1
            event_out.update({"code": code})
            verdicts.append({**event_out, "ok": True})

        elif etype == "POSE_LOST":
            pose_lost += 1
            event_out.update({"poseLostCount": pose_lost})
            verdicts.append({**event_out, "ok": True})

        else:  # QUALITY_LOW
            event_out.update({"confidence": confidence})
            verdicts.append({**event_out, "ok": True})

        accepted += 1
        event_count += 1

    new.update(
        repCount=rep_count,
        validRepCount=valid_reps,
        holdMs=hold_ms,
        eventCount=event_count,
        errorCounts=errors,
        lastErrorTs=last_code_ts,
        poseLostCount=pose_lost,
        confidenceSum=round(conf_sum, 4),
        confidenceN=conf_n,
        avgConfidence=round(conf_sum / conf_n, 4) if conf_n else float(new.get("avgConfidence", 0.0) or 0.0),
    )
    return {"counters": new, "verdicts": verdicts, "accepted": accepted}


def counters_out(
    counters: dict[str, Any],
    config: dict[str, Any],
    target_reps: int | None = None,
    target_seconds: int | None = None,
) -> dict[str, Any]:
    """Frontend-facing live counters for a session. Session-level target
    overrides (target_reps/target_seconds) win over the config defaults."""
    completion = config.get("completion", {})
    config_reps = completion.get("reps") if completion.get("type") == "REPS" else None
    config_seconds = completion.get("seconds") if completion.get("type") == "HOLD" else None
    return {
        "repCount": int(counters.get("repCount", 0) or 0),
        "validRepCount": int(counters.get("validRepCount", 0) or 0),
        "holdSeconds": round(int(counters.get("holdMs", 0) or 0) / 1000.0, 1),
        "poseLostCount": int(counters.get("poseLostCount", 0) or 0),
        "errorCounts": counters.get("errorCounts", {}) or {},
        "avgConfidence": float(counters.get("avgConfidence", 0.0) or 0.0),
        "targetReps": target_reps if target_reps is not None else config_reps,
        "targetSeconds": target_seconds if target_seconds is not None else config_seconds,
        "progressRatio": progress_ratio(config, counters, target_reps, target_seconds),
    }


def progress_ratio(
    config: dict[str, Any],
    counters: dict[str, Any],
    target_reps: int | None = None,
    target_seconds: int | None = None,
) -> float:
    completion = config.get("completion", {})
    if completion.get("type") == "HOLD":
        target = max(1, int(target_seconds if target_seconds is not None else completion.get("seconds", 1))) * 1000
        return _clamp(int(counters.get("holdMs", 0) or 0) / target, 0.0, 1.0)
    target = max(1, int(target_reps if target_reps is not None else completion.get("reps", 1)))
    return _clamp(int(counters.get("validRepCount", 0) or 0) / target, 0.0, 1.0)


def evaluate_completion(
    config: dict[str, Any],
    counters: dict[str, Any],
    target_reps: int | None = None,
    target_seconds: int | None = None,
) -> dict[str, Any]:
    """Backend truth check. The frontend can never claim completion itself."""
    completion = config.get("completion", {})
    if completion.get("type") == "HOLD":
        required = int(target_seconds if target_seconds is not None else completion.get("seconds", 0))
        actual = round(int(counters.get("holdMs", 0) or 0) / 1000.0, 1)
        met = actual >= required > 0
        return {"met": met, "type": "HOLD", "required": required, "actual": actual, "unit": "seconds"}
    required = int(target_reps if target_reps is not None else completion.get("reps", 0))
    actual = int(counters.get("validRepCount", 0) or 0)
    met = actual >= required > 0
    return {"met": met, "type": "REPS", "required": required, "actual": actual, "unit": "reps"}
