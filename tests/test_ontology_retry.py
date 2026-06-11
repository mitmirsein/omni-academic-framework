"""OntologyExtractor self-correcting 재시도 테스트 (QUALITY_IMPROVEMENT_PLAN.md F5)."""

import json

import pytest

from omni_academic.ontology.extractor import OntologyExtractor, OntologyMap
from omni_academic.supervisor import router as router_mod
from omni_academic.supervisor.router import (
    ModuleType,
    OmniSupervisorRouter,
    RouterRequest,
)
from omni_academic.text.paragraphs import assign_paragraph_ids

DOC = (
    "The first paragraph carries the main claim of the paper.\n\n"
    "The second paragraph develops the supporting argument in detail."
)


def _map(pid: str, quote: str) -> dict:
    return {
        "nodes": [{
            "id": "n1", "label": "Claim", "entity_class": "Concept",
            "paragraph_id": pid, "source_quote": quote,
        }],
        "edges": [],
    }


class CorrectingOntologyProvider:
    """1차: 환각 인용 → 2차: 교정된 인용 (재시도 루프 검증용)."""

    def __init__(self):
        self.calls = 0
        self.last_usage = None
        self.prompts = []

    def generate_structured_output(self, prompt, schema):
        self.calls += 1
        self.prompts.append(prompt)
        self.last_usage = {"model": "scripted", "mock": True, "calls": self.calls}
        if self.calls == 1:
            return schema.model_validate(_map("P_0001", "this quote was hallucinated"))
        return schema.model_validate(_map("P_0001", "carries the main claim"))


class AlwaysBadOntologyProvider:
    last_usage = {"model": "scripted", "mock": True}

    def generate_structured_output(self, prompt, schema):
        return schema.model_validate(_map("P_0999", "ghost quote"))


def test_extract_retries_with_correction_feedback():
    _, pmap = assign_paragraph_ids(DOC)
    provider = CorrectingOntologyProvider()
    extractor = OntologyExtractor(llm_provider=provider)
    result = extractor.extract(DOC, paragraph_map=pmap)
    assert provider.calls == 2
    assert extractor.last_attempts == 2
    assert result.nodes[0].source_quote == "carries the main claim"
    # 2차 프롬프트에 교정 지시와 구체 오류가 포함되어야 한다.
    assert "CORRECTION REQUIRED" in provider.prompts[1]
    assert "hallucinated" in provider.prompts[1]


def test_extract_returns_last_map_after_exhausted_retries():
    """재시도 소진 시 크래시 대신 마지막 맵 반환 — AuditGate가 결정론적으로 차단."""
    _, pmap = assign_paragraph_ids(DOC)
    extractor = OntologyExtractor(llm_provider=AlwaysBadOntologyProvider())
    result = extractor.extract(DOC, paragraph_map=pmap)
    assert extractor.last_attempts == 2
    assert isinstance(result, OntologyMap)
    assert result.nodes[0].paragraph_id == "P_0999"


def test_extract_without_paragraph_map_is_single_shot():
    provider = CorrectingOntologyProvider()
    extractor = OntologyExtractor(llm_provider=provider)
    extractor.extract(DOC)  # 검증 기준 없음 → 1회
    assert provider.calls == 1
    assert extractor.last_attempts == 1


@pytest.mark.anyio
async def test_router_records_ontology_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(
        router_mod, "_make_provider", lambda use_mock: CorrectingOntologyProvider(),
    )
    runs_base = tmp_path / "runs"
    router = OmniSupervisorRouter(use_mock=True, runs_base=str(runs_base))
    await router.route(RouterRequest(
        query=DOC, lens="general",
        target_module=ModuleType.ONTOLOGY, use_mock=True,
    ))

    manifests = list(runs_base.rglob("manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["audit_passed"] is True
    assert manifest["llm_usage"]["ontology_attempts"] == 2
    assert manifest["llm_usage"]["ontology"]["calls"] == 2
