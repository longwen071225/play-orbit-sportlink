"""SoloPilot configuration. Every Bailian setting comes from the environment.

The Python service uses a dedicated SOLOPILOT_ prefix on purpose: the legacy
Node/Fastify service in the same repository owns the root .env and defines a
different DASHSCOPE_MODEL (qwen-plus). Sharing bare names would silently
override the required qwen3.7-plus default. Real OS environment variables
always take precedence over backend/.env.

For convenience the common DASHSCOPE_API_KEY is also accepted as a fallback
source for SOLOPILOT_DASHSCOPE_API_KEY.
"""
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

if not os.environ.get("SOLOPILOT_DASHSCOPE_API_KEY") and os.environ.get("DASHSCOPE_API_KEY"):
    os.environ["SOLOPILOT_DASHSCOPE_API_KEY"] = os.environ["DASHSCOPE_API_KEY"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOLOPILOT_",
        env_file="backend/.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Alibaba Bailian (OpenAI-compatible) ----
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DASHSCOPE_MODEL: str = "qwen3.7-plus"
    DASHSCOPE_FALLBACK_MODEL: str = "qwen3.8-max"
    DASHSCOPE_REGION: str = "beijing"

    # ---- LLM behaviour ----
    # auto = real when a key is present, otherwise mock; mock/real force a mode.
    LLM_MODE: str = "auto"
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_BASE_DELAY: float = 0.5

    # ---- Tool loop ----
    MAX_TOOL_ROUNDS: int = 6
    # Simulates a region/model without Function Calling; exercises the fallback.
    FORCE_STATE_MACHINE: bool = False

    # ---- Database (reuses the existing Prisma SQLite file) ----
    DATABASE_PATH: str = "prisma/dev.db"

    # ---- Seed values for the DB-backed price list ----
    PRICE_SINGLE_CENTS: int = 12900
    PRICE_PACKAGE4_CENTS: int = 49900
    PACKAGE_SESSIONS: int = 4

    # ---- StarFit platform ----
    # Server-side secret for HMAC auth tokens. Override in production.
    STARFIT_SECRET: str = ""
    # Seed demo users/coaches/exercises on startup when sf_user is empty.
    STARFIT_SEED_DEMO: bool = True

    # ---- Motion Coach (SportLink MVP 1.1) ----
    # Optional faster/cheaper model for short coaching utterances. Empty = the
    # primary model. Real model names must exist in the Bailian region in use.
    FAST_MODEL: str = ""
    # Max batches of pose events accepted per feedback request (burst guard).
    POSE_MAX_EVENTS_PER_REQUEST: int = 100

    @property
    def api_key_present(self) -> bool:
        return bool(self.DASHSCOPE_API_KEY.strip())

    @property
    def resolved_mode(self) -> str:
        if self.LLM_MODE == "mock":
            return "mock"
        if self.LLM_MODE == "real":
            return "real"
        return "real" if self.api_key_present else "mock"


settings = Settings()
