"""AnthropicProvider 런타임 방어선 테스트 (QUALITY_IMPROVEMENT_PLAN.md F4).

실 `anthropic` 패키지 없이 fake client로 응답 경계를 고정한다:
- max_tokens truncation은 침묵 진행 대신 hard fail해야 한다.
- usage 기록은 실패 경로에서도 남아야 한다(운용 감사).
"""

import pytest

from omni_academic.llm.provider import AnthropicProvider
from omni_academic.ontology.extractor import OntologyMap


class _FakeAnthropicModule:
    class APIError(Exception):
        pass


class _FakeUsage:
    input_tokens = 1200
    output_tokens = 16000
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _FakeToolBlock:
    type = "tool_use"
    input = {"nodes": [], "edges": []}


class _FakeResponse:
    def __init__(self, stop_reason: str, content=None):
        self.model = "claude-test"
        self.stop_reason = stop_reason
        self.usage = _FakeUsage()
        self.content = content if content is not None else []


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.messages = self

    def create(self, **kwargs):
        return self._response


def _provider(response) -> AnthropicProvider:
    # __init__은 실 패키지/키를 요구하므로 fake 협력자만 직접 주입한다.
    provider = object.__new__(AnthropicProvider)
    provider._anthropic = _FakeAnthropicModule
    provider.client = _FakeClient(response)
    provider.model = "claude-test"
    provider.max_tokens = 1024
    provider.last_usage = None
    return provider


def test_max_tokens_truncation_hard_fails_with_guidance():
    provider = _provider(_FakeResponse("max_tokens", content=[_FakeToolBlock()]))
    with pytest.raises(RuntimeError, match="OMNI_LLM_MAX_TOKENS"):
        provider.generate_structured_output("prompt", OntologyMap)
    # 실패해도 usage는 기록되어야 비용/원인 감사가 가능하다.
    assert provider.last_usage["stop_reason"] == "max_tokens"
    assert provider.last_usage["schema"] == "OntologyMap"


def test_normal_stop_reason_returns_validated_schema():
    provider = _provider(_FakeResponse("tool_use", content=[_FakeToolBlock()]))
    result = provider.generate_structured_output("prompt", OntologyMap)
    assert isinstance(result, OntologyMap)
    assert provider.last_usage["stop_reason"] == "tool_use"


def test_missing_tool_block_still_raises():
    provider = _provider(_FakeResponse("end_turn", content=[]))
    with pytest.raises(RuntimeError, match="tool_use"):
        provider.generate_structured_output("prompt", OntologyMap)
