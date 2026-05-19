import pytest

from src.config.lens import (
    LensNotFoundError,
    get_recon_client_names,
    load_lens,
)
from src.audit.gate import AuditGate
from src.analyze.lens_analyzer import LensAnalyzer
from src.llm.provider import AnthropicProvider, MockProvider
from src.ontology.extractor import OntologyMap
from src.recon.engine import ArxivClient, CrossrefClient, ReconEngine
from src.text.paragraphs import assign_paragraph_ids


def test_load_lens_reads_yaml():
    cfg = load_lens("cs")
    assert cfg["name"] == "Computer Science"
    assert get_recon_client_names(cfg) == ["arxiv", "crossref"]


def test_load_lens_missing_raises():
    with pytest.raises(LensNotFoundError):
        load_lens("does-not-exist")


def test_recon_clients_are_config_driven():
    engine = ReconEngine()
    clients = engine._resolve_clients("cs")
    types = {type(c) for c in clients}
    assert ArxivClient in types and CrossrefClient in types


def test_recon_unknown_lens_falls_back_to_general():
    engine = ReconEngine()
    clients = engine._resolve_clients("nonexistent-domain")
    # general.yaml → crossref
    assert any(isinstance(c, CrossrefClient) for c in clients)


def test_anthropic_provider_requires_api_key():
    # 빈 키는 설정 오류 → ValueError (router가 --mock 안내와 함께 처리)
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="")


def test_mock_provider_uses_real_paragraph_ids_and_quotes():
    annotated, paragraph_map = assign_paragraph_ids("Alpha claim appears here.\n\nBeta method follows.")
    ontology = MockProvider().generate_structured_output(annotated, OntologyMap)

    assert [n.paragraph_id for n in ontology.nodes] == ["P_0001", "P_0002"]
    assert all(n.source_quote for n in ontology.nodes)

    report = AuditGate().verify_ontology(ontology, paragraph_manifest=paragraph_map)
    assert report.passed


def test_lens_analyzer_builds_source_bound_brief():
    brief = LensAnalyzer().build_brief(
        "Alpha claim appears here.\n\nBeta method follows.",
        "general",
    )

    assert "# Lens Briefing Scaffold" in brief
    assert "General Academic" in brief
    assert "P_0001" in brief
    assert "Alpha claim appears here." in brief
    assert "Review Questions" in brief
