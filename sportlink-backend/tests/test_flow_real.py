"""Real Alibaba Bailian API tests.

These are SKIPPED unless both conditions hold:
  * SOLOPILOT_DASHSCOPE_API_KEY (or DASHSCOPE_API_KEY) is present
  * SOLOPILOT_REAL_TEST=true is set explicitly

A skipped test is reported as skipped, never as passed. When executed, the
actual probe result, model reply, latency and token usage are printed to the
pytest output (-s) so the numbers can be verified rather than assumed.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.llm import BailianClient

REAL_KEY = (
    os.environ.get("SOLOPILOT_DASHSCOPE_API_KEY", "").strip()
    or os.environ.get("DASHSCOPE_API_KEY", "").strip()
)
REAL_ENABLED = os.environ.get("SOLOPILOT_REAL_TEST", "").lower() in {"1", "true", "yes"}
BASE_URL = os.environ.get(
    "SOLOPILOT_DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
MODEL = os.environ.get("SOLOPILOT_DASHSCOPE_MODEL", "qwen3.7-plus")
FALLBACK = os.environ.get("SOLOPILOT_DASHSCOPE_FALLBACK_MODEL", "qwen3.8-max")
REGION = os.environ.get("SOLOPILOT_DASHSCOPE_REGION", "beijing")

SKIP_REASON = (
    "真实百炼 API 测试未执行："
    + ("缺少 DASHSCOPE_API_KEY" if not REAL_KEY else "未设置 SOLOPILOT_REAL_TEST=true")
)

pytestmark = pytest.mark.real_bailian


@pytest.mark.skipif(not (REAL_KEY and REAL_ENABLED), reason=SKIP_REASON)
def test_real_bailian_connectivity_function_calling_and_chat(raw):
    cfg = Settings(
        LLM_MODE="real",
        DASHSCOPE_API_KEY=REAL_KEY,
        DASHSCOPE_BASE_URL=BASE_URL,
        DASHSCOPE_MODEL=MODEL,
        DASHSCOPE_FALLBACK_MODEL=FALLBACK,
        DASHSCOPE_REGION=REGION,
        LLM_TIMEOUT_SECONDS=float(os.environ.get("SOLOPILOT_LLM_TIMEOUT_SECONDS", "30")),
        LLM_MAX_RETRIES=int(os.environ.get("SOLOPILOT_LLM_MAX_RETRIES", "1")),
        DATABASE_PATH=os.environ["SOLOPILOT_DATABASE_PATH"],
        FORCE_STATE_MACHINE=False,
    )
    llm = BailianClient(cfg)
    assert llm.mode == "real"
    assert llm.primary_model == MODEL
    assert llm.fallback_model == FALLBACK

    probe = llm.probe()
    print("\n[REAL BAILIAN PROBE]", probe)
    assert probe["checked"] is True
    # Do NOT assert fcSupported == True: it is region/model dependent by design.
    # A negative result must be reported and must switch to the fallback path.
    assert llm.use_state_machine == (not probe["fcSupported"])

    app = create_app(llm)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ai/chat",
            json={
                "message": "你好，想咨询8岁孩子的上门体育训练，麻烦先了解一下我们的需求",
                "parentName": "真实测试家长（虚构）",
                "contact": "demo-real-bailian",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        print("[REAL BAILIAN CHAT]", body["data"]["reply"])
        print("[REAL BAILIAN TOKENS]", body["data"]["tokenUsage"])
        assert body["success"] is True
        data = body["data"]
        assert data["llmMode"] == "real"
        assert data["reply"]
        assert data["tokenUsage"]["calls"] >= 1
        assert data["mode"] in {"function_calling", "state_machine_fallback"}

    # Real business records must exist regardless of which tools the model chose.
    assert raw.execute('SELECT COUNT(*) FROM "Lead"').fetchone()[0] == 1
    assert raw.execute('SELECT COUNT(*) FROM "Message"').fetchone()[0] >= 2
    assert raw.execute('SELECT COUNT(*) FROM "AgentRun"').fetchone()[0] == 1
    assert raw.execute('SELECT COUNT(*) FROM "AgentAction"').fetchone()[0] >= 2
