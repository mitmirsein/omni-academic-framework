"""LLM usage 누적 로그 테스트 (QUALITY_IMPROVEMENT_PLAN.md F8).

재시도가 발생해도 모든 호출의 토큰 비용이 manifest에서 추적 가능해야 한다.
"""

import json

import pytest

from omni_academic.llm.provider import MockProvider
from omni_academic.ontology.extractor import OntologyMap
from omni_academic.supervisor.router import (
    ModuleType,
    OmniSupervisorRouter,
    RouterRequest,
    _provider_usage,
)


def test_mock_provider_accumulates_usage_log():
    provider = MockProvider()
    provider.generate_structured_output("[P_0001] alpha beta", OntologyMap)
    provider.generate_structured_output("[P_0001] alpha beta", OntologyMap)
    assert len(provider.usage_log) == 2
    assert provider.last_usage is provider.usage_log[-1]


def test_usage_log_is_per_instance_not_shared():
    a, b = MockProvider(), MockProvider()
    a.generate_structured_output("[P_0001] alpha", OntologyMap)
    assert a.usage_log and not b.usage_log  # 클래스 속성 공유 사고 방지


def test_provider_usage_sums_token_totals():
    class _Fake:
        last_usage = {"input_tokens": 200, "output_tokens": 80}
        usage_log = [
            {"input_tokens": 100, "output_tokens": 40},
            {"input_tokens": 200, "output_tokens": 80},
            {"input_tokens": None, "output_tokens": None},  # 결측은 합산 제외
        ]

    out = _provider_usage("draft", _Fake(), attempts=2)
    assert out["draft"] == _Fake.last_usage
    assert out["draft_attempts"] == 2
    assert len(out["draft_calls"]) == 3
    assert out["draft_total_input_tokens"] == 300
    assert out["draft_total_output_tokens"] == 120


def test_provider_usage_tolerates_ducktyped_providers_without_log():
    class _Bare:
        last_usage = {"model": "scripted"}

    out = _provider_usage("review", _Bare(), attempts=1)
    assert out == {"review": {"model": "scripted"}, "review_attempts": 1}


@pytest.mark.anyio
async def test_draft_run_manifest_records_per_step_calls(tmp_path):
    doc = "First paragraph with enough words.\n\nSecond paragraph with more words."
    runs_base = tmp_path / "runs"
    router = OmniSupervisorRouter(use_mock=True, runs_base=str(runs_base))
    await router.route(RouterRequest(
        query=doc, lens="general",
        target_module=ModuleType.DRAFT, use_mock=True,
    ))

    manifests = list(runs_base.rglob("manifest.json"))
    assert len(manifests) == 1
    usage = json.loads(manifests[0].read_text(encoding="utf-8"))["llm_usage"]
    # ontology 단계가 draft 단계 기록에 덮이지 않고 병합 유지된다.
    assert usage["ontology_attempts"] == 1
    assert len(usage["ontology_calls"]) == 1
    assert usage["draft_attempts"] == 1
    assert len(usage["draft_calls"]) == 1
    assert usage["draft"]["mock"] is True
