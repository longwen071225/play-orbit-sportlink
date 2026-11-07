"""Alibaba Bailian via the official Python OpenAI SDK (OpenAI-compatible mode).

Responsibilities:
  * primary model qwen3.7-plus, fallback qwen3.8-max (env-configurable)
  * timeout, bounded retries with backoff, fallback-model switch, error wrapping
  * per-request and per-run token accounting
  * Function Calling capability probe + explicit state-machine fallback signal
  * a deterministic offline model that emits genuine tool_calls, so the whole
    tool loop can be exercised without an API key
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from .config import settings
from .plans import build_stage_plan


class LLMError(RuntimeError):
    pass


@dataclass
class TokenStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    models: set[str] = field(default_factory=set)

    def add(self, usage: dict[str, int], model: str) -> None:
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.total_tokens += int(usage.get("total_tokens") or 0)
        self.calls += 1
        self.models.add(model)

    def as_dict(self) -> dict[str, Any]:
        return {
            "promptTokens": self.prompt_tokens,
            "completionTokens": self.completion_tokens,
            "totalTokens": self.total_tokens,
            "calls": self.calls,
            "models": sorted(self.models),
        }


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[dict[str, Any]]
    usage: dict[str, int]
    model: str
    finish_reason: str | None = None


# --------------------------------------------------------------------- mock
class MockLLM:
    """Offline stand-in. It returns real `tool_calls` structures; the backend
    then validates and executes them exactly as it would for Bailian."""

    @staticmethod
    def _call(index: int, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f"mock_call_{index}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        }

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> LLMResponse:
        # Once tool results are appended, the model produces its final answer.
        if messages and messages[-1].get("role") == "tool":
            return LLMResponse(
                content=self._final_text(context, messages),
                tool_calls=[],
                usage={"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165},
                model="mock",
            )

        steps = build_stage_plan(context)
        calls = [self._call(i + 1, s["name"], s["args"]) for i, s in enumerate(steps)]
        return LLMResponse(
            content=None,
            tool_calls=calls,
            usage={"prompt_tokens": 180 + len(calls) * 20, "completion_tokens": 60, "total_tokens": 240 + len(calls) * 20},
            model="mock",
        )

    @staticmethod
    def _final_text(context: dict[str, Any], messages: list[dict[str, Any]]) -> str:
        tool_results = [m.get("content", "") for m in messages if m.get("role") == "tool"]
        stage = context.get("stage", "greet")
        if stage == "greet":
            return "您好，感谢咨询！为了给孩子安排合适的上门训练，想先确认一下：孩子几岁、想练什么、什么时间方便上课？"
        if stage == "info_complete":
            return "已为孩子生成四周课程方案，并查询了当前价目表。正式报价需要您确认后才会生成，请回复「确认报价」。"
        if stage == "quote_confirm":
            return "报价已生成并存档，金额由系统按数据库价目表计算。需要预约的话请把方便的上课时间告诉我。"
        if stage == "booking_request":
            return "该时段档期已查询，预约需要您确认后才会创建，请回复「确认预约」。"
        if stage == "booking_confirm":
            return "已为您创建待确认预约，教练会按时上门；后续如需调整时间随时告诉我。"
        if stage == "done":
            return "之前的方案和预约都已办妥，还有什么可以帮您？"
        if stage == "awaiting_confirmation":
            return "这一步需要您明确确认，请在请求中回传 confirmationId。"
        if stage == "fallback_final":
            return "已完成本轮处理（状态机降级模式）。"
        return f"已完成本轮处理（{len(tool_results)} 个工具调用）。"


# --------------------------------------------------------------------- real
class BailianClient:
    def __init__(self, config: Any = None) -> None:
        self.config = config or settings
        self.mode = self.config.resolved_mode
        if self.mode == "real" and not self.config.api_key_present:
            raise LLMError(
                "LLM_MODE=real 但未配置 DASHSCOPE_API_KEY：请填写百炼 Key"
                "（注意北京/新加坡/香港 Key 与 base_url 不通用），"
                "或设置 LLM_MODE=mock 使用离线演示模式"
            )
        self.primary_model = self.config.DASHSCOPE_MODEL
        self.fallback_model = self.config.DASHSCOPE_FALLBACK_MODEL
        self.timeout = self.config.LLM_TIMEOUT_SECONDS
        self.retries = max(0, self.config.LLM_MAX_RETRIES)
        self.mock = MockLLM()
        self.client: OpenAI | None = None
        self.fc_supported = False
        self.fc_reason = ""
        self.probe_result: dict[str, Any] = {}

        if self.mode == "real" and self.config.api_key_present:
            self.client = OpenAI(
                api_key=self.config.DASHSCOPE_API_KEY,
                base_url=self.config.DASHSCOPE_BASE_URL,
                timeout=self.timeout,
                max_retries=0,  # we own the retry policy
            )

    # ------------------------------------------------------------------ chat
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
        tool_choice: str = "auto",
        model_override: str | None = None,
    ) -> LLMResponse:
        if self.mode == "mock" or self.client is None:
            return self.mock.chat(messages, tools, context or {"leadId": ""})

        kwargs: dict[str, Any] = {
            "model": (model_override or "").strip() or self.primary_model,
            "messages": messages,
            "temperature": 0.2,
            "timeout": self.timeout,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.client.chat.completions.create(**kwargs)
                return self._parse_response(response, kwargs["model"])
            except Exception as exc:  # noqa: BLE001 - wrapped into LLMError below
                last_error = exc
                if self._is_model_error(exc) and kwargs["model"] != self.fallback_model:
                    # Switch to qwen3.8-max once, then keep retrying on it.
                    kwargs["model"] = self.fallback_model
                    continue
                if attempt < self.retries:
                    time.sleep(self.config.LLM_RETRY_BASE_DELAY * (2**attempt))
        raise LLMError(f"百炼调用失败（模型 {kwargs['model']}，尝试 {self.retries + 1} 次）：{last_error}")

    @staticmethod
    def _is_model_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return any(
            key in text
            for key in ("model", "model_not_found", "invalid model", "not found", "does not exist", "404")
        )

    @staticmethod
    def _parse_response(response: Any, model: str) -> LLMResponse:
        choice = response.choices[0]
        message = choice.message
        calls: list[dict[str, Any]] = []
        for tc in getattr(message, "tool_calls", None) or []:
            calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
            )
        usage_obj = getattr(response, "usage", None)
        usage = {
            "prompt_tokens": int(getattr(usage_obj, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage_obj, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(usage_obj, "total_tokens", 0) or 0),
        }
        return LLMResponse(
            content=message.content,
            tool_calls=calls,
            usage=usage,
            model=model,
            finish_reason=getattr(choice, "finish_reason", None),
        )

    # ----------------------------------------------------------------- probe
    def probe(self) -> dict[str, Any]:
        """Connectivity + Function Calling support check, run at startup/health."""
        result: dict[str, Any] = {
            "checked": True,
            "mode": self.mode,
            "region": self.config.DASHSCOPE_REGION,
            "baseUrl": self.config.DASHSCOPE_BASE_URL,
            "primaryModel": self.primary_model,
            "fallbackModel": self.fallback_model,
            "fcSupported": False,
            "reason": "",
            "latencyMs": 0,
            "replyTokens": 0,
        }

        if self.config.FORCE_STATE_MACHINE:
            result["reason"] = "FORCE_STATE_MACHINE=true：按要求模拟地域/模型不支持 Function Calling，已启用状态机降级"
            self.probe_result = result
            self.fc_supported = False
            self.fc_reason = result["reason"]
            return result

        if self.mode == "mock" or self.client is None:
            result["fcSupported"] = True
            result["reason"] = "mock 模式：不发起真实网络请求，Function Calling 循环由离线模型驱动"
            self.probe_result = result
            self.fc_supported = True
            self.fc_reason = result["reason"]
            return result

        ping_tools = [
            {
                "type": "function",
                "function": {
                    "name": "connectivity_ping",
                    "description": "Return a pong to confirm tools are accepted",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            }
        ]
        started = time.time()
        try:
            response = self.chat(
                [{"role": "user", "content": "请调用 connectivity_ping 确认连通性"}],
                tools=ping_tools,
            )
            result["fcSupported"] = True
            result["reason"] = "百炼 OpenAI 兼容接口接受了 tools 参数，连通性正常"
            result["replyTokens"] = response.usage.get("total_tokens", 0)
        except Exception as exc:  # noqa: BLE001 - probe must never crash startup
            result["fcSupported"] = False
            result["reason"] = f"Function Calling 探测失败，已启用状态机降级：{exc}"
        result["latencyMs"] = int((time.time() - started) * 1000)
        self.probe_result = result
        self.fc_supported = result["fcSupported"]
        self.fc_reason = result["reason"]
        return result

    @property
    def use_state_machine(self) -> bool:
        if not self.probe_result:
            self.probe()
        return self.config.FORCE_STATE_MACHINE or not self.fc_supported
