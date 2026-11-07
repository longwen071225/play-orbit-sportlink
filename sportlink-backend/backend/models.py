"""Pydantic schemas. Tool arguments use extra="forbid" so a model cannot smuggle
unexpected keys past the whitelist boundary.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ tool args
class ReceptionGetLeadArgs(StrictModel):
    lead_id: str = Field(min_length=1)


class ReceptionUpdateLeadFieldsArgs(StrictModel):
    lead_id: str = Field(min_length=1)
    child_age: int | None = Field(default=None, ge=1, le=18)
    goal: str | None = Field(default=None, max_length=300)
    experience: str | None = Field(default=None, max_length=300)
    available_time: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=200)


class ReceptionAskMissingInfoArgs(StrictModel):
    lead_id: str = Field(min_length=1)
    missing_fields: list[str] = Field(min_length=1, max_length=10)


class PlanCreateTrainingPlanArgs(StrictModel):
    lead_id: str = Field(min_length=1)
    age: int = Field(ge=1, le=18)
    goal: str = Field(min_length=1, max_length=300)
    experience: str = Field(min_length=1, max_length=300)


class BusinessGetPriceListArgs(StrictModel):
    pass


class BusinessCalculateQuoteArgs(StrictModel):
    lead_id: str = Field(min_length=1)
    package_type: Literal["single", "package4"]
    quantity: int = Field(ge=1, le=20)
    confirmation_id: str = Field(min_length=1, description="User-supplied token; the model cannot mint it")


class OperationsCheckAvailabilityArgs(StrictModel):
    start_at: str = Field(min_length=1, description="ISO-8601 with offset")
    end_at: str = Field(min_length=1, description="ISO-8601 with offset")


class OperationsCreateBookingArgs(StrictModel):
    lead_id: str = Field(min_length=1)
    start_at: str = Field(min_length=1)
    end_at: str = Field(min_length=1)
    note: str | None = Field(default=None, max_length=500)
    confirmation_id: str = Field(min_length=1)


class OperationsCreateFollowupDraftArgs(StrictModel):
    lead_id: str = Field(min_length=1)
    channel: Literal["wechat", "sms", "phone", "in_app"] = "wechat"


class SharedRequestConfirmationArgs(StrictModel):
    action: Literal["calculate_quote", "create_booking"]
    summary: str = Field(min_length=1, max_length=300)


# ------------------------------------------------------------------ API
class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=4000)
    leadId: str | None = None
    sessionId: str | None = None
    parentName: str | None = Field(default=None, max_length=60)
    contact: str | None = Field(default=None, max_length=120)
    confirmationId: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class Envelope(BaseModel):
    """Same contract as the legacy service: {success,data,error,requestId}."""
    success: bool
    data: Any | None = None
    error: ErrorBody | None = None
    requestId: str
