"""One source of truth for the tool sequence of each conversation stage.

Both the offline mock model (which emits tool_calls) and the state-machine
fallback (which calls tools directly) use build_stage_plan(), so the two paths
execute exactly the same whitelisted functions with the same arguments.
"""
from __future__ import annotations

from typing import Any


def build_stage_plan(context: dict[str, Any]) -> list[dict[str, Any]]:
    stage = context.get("stage", "greet")
    lead_id = context["leadId"]
    cid = context.get("confirmationId") or ""
    start = context.get("proposedStartAt", "")
    end = context.get("proposedEndAt", "")
    extracted = context.get("extracted", {})

    if stage == "greet":
        return [
            {"name": "reception_get_lead", "args": {"lead_id": lead_id}},
            {
                "name": "reception_ask_missing_info",
                "args": {"lead_id": lead_id, "missing_fields": ["childAge", "goal", "availableTime"]},
            },
        ]

    if stage == "info_complete":
        update_args = {"lead_id": lead_id}
        update_args.update({k: v for k, v in extracted.items() if v is not None})
        return [
            {"name": "reception_update_lead_fields", "args": update_args},
            {
                "name": "plan_create_training_plan",
                "args": {
                    "lead_id": lead_id,
                    "age": extracted.get("child_age") or 8,
                    "goal": extracted.get("goal") or "体能训练",
                    "experience": extracted.get("experience") or "零基础",
                },
            },
            {"name": "business_get_price_list", "args": {}},
            {
                "name": "shared_request_confirmation",
                "args": {"action": "calculate_quote", "summary": "将按四节套餐生成正式报价单，请家长确认"},
            },
        ]

    if stage == "quote_confirm":
        return [
            {
                "name": "business_calculate_quote",
                "args": {
                    "lead_id": lead_id,
                    "package_type": "package4",
                    "quantity": 1,
                    "confirmation_id": cid,
                },
            }
        ]

    if stage == "booking_request":
        return [
            {"name": "operations_check_availability", "args": {"start_at": start, "end_at": end}},
            {
                "name": "shared_request_confirmation",
                "args": {"action": "create_booking", "summary": "将创建待确认上门训练预约，请家长确认"},
            },
        ]

    if stage == "booking_confirm":
        return [
            {
                "name": "operations_create_booking",
                "args": {
                    "lead_id": lead_id,
                    "start_at": start,
                    "end_at": end,
                    "note": "家长已确认的上门训练",
                    "confirmation_id": cid,
                },
            }
        ]

    # awaiting_confirmation / done -> no tools
    return []
