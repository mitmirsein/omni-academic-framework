from pathlib import Path

from omni_academic.llm.provider import (
    DEFAULT_LIVE_PROVIDER_ENV_VAR,
    RESERVED_PROVIDER_ENV_VARS,
    SUPPORTED_PROVIDER_NAMES,
)


def test_status_does_not_present_reserved_providers_as_active_options():
    status_source = Path("omni_academic/supervisor/status.py").read_text(encoding="utf-8")

    assert "ChatGPT 모델 분석 및 본문 가공" not in status_source
    assert "Gemini 다차원 분석 및 요약" not in status_source
    assert "Configured but reserved" in status_source
    assert "기본 live LLM provider" in status_source


def test_provider_boundary_constants_are_current_contract():
    assert DEFAULT_LIVE_PROVIDER_ENV_VAR == "ANTHROPIC_API_KEY"
    assert SUPPORTED_PROVIDER_NAMES == ("AnthropicProvider", "MockProvider")
    assert RESERVED_PROVIDER_ENV_VARS == ("OPENAI_API_KEY", "GEMINI_API_KEY")
