"""동적 용어집 MVP 테스트 (QUALITY_IMPROVEMENT_PLAN.md F12, 헌법 §4)."""

import json

import pytest

from omni_academic.analyze.glossary import (
    GlossaryBuilder,
    GlossaryReport,
    GlossaryTerm,
)
from omni_academic.llm.provider import MockProvider
from omni_academic.supervisor import router as router_mod
from omni_academic.supervisor.router import (
    ModuleType,
    OmniSupervisorRouter,
    RouterRequest,
)
from omni_academic.text.paragraphs import assign_paragraph_ids

DOC = (
    "Kenosis describes the self-emptying movement of the divine subject.\n\n"
    "The aporia of dual natures resists every speculative synthesis attempted."
)


def test_builder_extracts_grounded_terms_with_mock():
    builder = GlossaryBuilder()
    report = builder.build(DOC, MockProvider())
    assert report.terms
    _, pmap = assign_paragraph_ids(DOC)
    audit = builder.verify(report, pmap)
    assert audit.passed
    assert builder.last_attempts == 1


def test_verify_blocks_foreign_term_and_hallucinated_quote():
    _, pmap = assign_paragraph_ids(DOC)
    report = GlossaryReport(terms=[
        GlossaryTerm(
            term="Dasein",  # 원문에 없는 외부 용어
            definition="imported from outside",
            paragraph_id="P_0001",
            source_quote="Kenosis describes the self-emptying movement",
        ),
        GlossaryTerm(
            term="Kenosis",
            definition="ok term, bad quote",
            paragraph_id="P_0001",
            source_quote="this quote is hallucinated",
        ),
        GlossaryTerm(
            term="Kenosis",
            definition="ok term, unknown paragraph",
            paragraph_id="P_0999",
            source_quote="whatever",
        ),
    ])
    audit = GlossaryBuilder.verify(report, pmap)
    assert not audit.passed
    codes = {f.code for f in audit.findings}
    assert {
        "FOREIGN_GLOSSARY_TERM",
        "UNGROUNDED_GLOSSARY_QUOTE",
        "UNGROUNDED_GLOSSARY_TERM",
    } <= codes


class BadGlossaryProvider(MockProvider):
    """용어집만 환각으로 생성 — fail-closed(주입 차단) 검증용."""

    def generate_structured_output(self, prompt, schema):
        if schema.__name__ == "GlossaryReport":
            return schema.model_validate({
                "terms": [{
                    "term": "PhantomTerm",
                    "definition": "does not exist in source",
                    "paragraph_id": "P_0001",
                    "source_quote": "hallucinated quote",
                }],
                "style_notes": [],
            })
        return super().generate_structured_output(prompt, schema)


class RecordingProvider(MockProvider):
    def __init__(self):
        self.prompts = []

    def generate_structured_output(self, prompt, schema):
        self.prompts.append((schema.__name__, prompt))
        return super().generate_structured_output(prompt, schema)


@pytest.mark.anyio
async def test_draft_run_with_glossary_injects_verified_block(tmp_path, monkeypatch):
    provider = RecordingProvider()
    monkeypatch.setattr(router_mod, "_make_provider", lambda use_mock: provider)

    runs_base = tmp_path / "runs"
    router = OmniSupervisorRouter(use_mock=True, runs_base=str(runs_base))
    await router.route(RouterRequest(
        query=DOC, lens="general",
        target_module=ModuleType.DRAFT, use_mock=True, glossary=True,
    ))

    manifests = list(runs_base.rglob("manifest.json"))
    assert len(manifests) == 1
    run_out = manifests[0].parent
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["glossary_audit_passed"] is True
    assert (run_out / "glossary.json").is_file()
    assert (run_out / "glossary.md").is_file()
    assert (run_out / "glossary_audit.json").is_file()
    # usage가 glossary/ontology/draft 단계 모두 병합 기록된다
    usage = manifest["llm_usage"]
    assert "glossary" in usage and "ontology" in usage and "draft" in usage

    # 검증된 용어집 블록이 draft 프롬프트에 실제 주입되었는지
    draft_prompts = [p for s, p in provider.prompts if s == "DraftReport"]
    assert draft_prompts
    assert "Verified Dynamic Glossary" in draft_prompts[0]


@pytest.mark.anyio
async def test_failed_glossary_is_not_injected(tmp_path, monkeypatch):
    provider = BadGlossaryProvider()
    prompts = []
    original = BadGlossaryProvider.generate_structured_output

    def recording(self, prompt, schema):
        prompts.append((schema.__name__, prompt))
        return original(self, prompt, schema)

    monkeypatch.setattr(BadGlossaryProvider, "generate_structured_output", recording)
    monkeypatch.setattr(router_mod, "_make_provider", lambda use_mock: provider)

    runs_base = tmp_path / "runs"
    router = OmniSupervisorRouter(use_mock=True, runs_base=str(runs_base))
    await router.route(RouterRequest(
        query=DOC, lens="general",
        target_module=ModuleType.DRAFT, use_mock=True, glossary=True,
    ))

    manifests = list(runs_base.rglob("manifest.json"))
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    # 진단 artifact는 남되, 반려된 용어집은 주입되지 않는다 (fail-closed)
    assert manifest["glossary_audit_passed"] is False
    assert manifest["status"] == "completed"  # 메인 흐름은 차단하지 않음
    draft_prompts = [p for s, p in prompts if s == "DraftReport"]
    assert draft_prompts
    assert "Verified Dynamic Glossary" not in draft_prompts[0]
    assert "PhantomTerm" not in draft_prompts[0]


@pytest.mark.anyio
async def test_glossary_off_by_default(tmp_path):
    runs_base = tmp_path / "runs"
    router = OmniSupervisorRouter(use_mock=True, runs_base=str(runs_base))
    await router.route(RouterRequest(
        query=DOC, lens="general",
        target_module=ModuleType.DRAFT, use_mock=True,
    ))
    manifests = list(runs_base.rglob("manifest.json"))
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert "glossary_audit_passed" not in manifest
    assert not (manifests[0].parent / "glossary.json").exists()
