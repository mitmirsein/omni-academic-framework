from pathlib import Path

from omni_academic.llm.provider import (
    DEFAULT_LIVE_PROVIDER_ENV_VAR,
    RESERVED_PROVIDER_ENV_VARS,
    SUPPORTED_PROVIDER_NAMES,
)
from omni_academic.supervisor.status import SETUP_QUESTIONS, _diagnostic_rows


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


def test_setup_questions_skip_reserved_provider_keys():
    env_vars = [question.env_var for question in SETUP_QUESTIONS]

    assert DEFAULT_LIVE_PROVIDER_ENV_VAR in env_vars
    assert "OPENAI_API_KEY" not in env_vars
    assert "GEMINI_API_KEY" not in env_vars


def test_diagnostic_rows_mark_reserved_provider_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "reserved-openai")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    rows, context = _diagnostic_rows()
    by_name = {row.name: row for row in rows}

    assert context["anthropic_key"] == ""
    assert by_name["OPENAI_API_KEY"].status == "[dim]Configured but reserved[/dim]"
    assert by_name["GEMINI_API_KEY"].status == "[dim]Reserved (not used)[/dim]"
    assert "기본 live path에서는 사용하지 않습니다" in by_name["OPENAI_API_KEY"].description
