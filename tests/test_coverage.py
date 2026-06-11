"""CoverageAuditor — 토큰 비율 방어선 테스트 (QUALITY_IMPROVEMENT_PLAN.md F3)."""

import json

import pytest

from omni_academic.audit.coverage import CoverageAuditor
from omni_academic.supervisor.router import (
    ModuleType,
    OmniSupervisorRouter,
    RouterRequest,
)


def _pmap(n: int, tokens_each: int = 10) -> dict:
    return {f"P_{i:04d}": "word " * tokens_each for i in range(1, n + 1)}


def test_measure_basic_coverage_and_token_ratio():
    report = CoverageAuditor().measure(
        _pmap(6), ["P_0001", "P_0002", "P_0999"], "out " * 30,
    )
    assert report.paragraph_count == 6
    # 실존 문단 앵커만 계수(P_0999는 무시)
    assert report.covered_paragraph_count == 2
    assert report.paragraph_coverage == round(2 / 6, 4)
    # tail = 마지막 1/3 구간(2개 문단), 어느 것도 앵커되지 않음
    assert report.tail_paragraph_count == 2
    assert report.tail_covered_count == 0
    assert report.tail_coverage == 0.0
    assert report.source_tokens == 60
    assert report.output_tokens == 30
    assert report.token_ratio == 0.5
    assert report.findings == []


def test_measure_tail_anchor_is_detected():
    report = CoverageAuditor().measure(_pmap(3, 1), ["P_0003"], "x")
    assert report.tail_paragraph_count == 1
    assert report.tail_coverage == 1.0


def test_empty_document_yields_zero_metrics():
    report = CoverageAuditor().measure({}, [], "")
    assert report.paragraph_count == 0
    assert report.paragraph_coverage == 0.0
    assert report.tail_paragraph_count == 0
    assert report.token_ratio == 0.0
    assert report.findings == []


def test_lens_thresholds_emit_warning_findings():
    report = CoverageAuditor().measure(
        {"P_0001": "a b c", "P_0002": "d e f"},
        ["P_0001"],
        "many output words here " * 5,
        thresholds={
            "min_paragraph_coverage": 0.9,
            "min_tail_coverage": 0.5,
            "max_token_ratio": 0.1,
        },
    )
    codes = {f.code for f in report.findings}
    assert codes == {
        "LOW_PARAGRAPH_COVERAGE", "LOW_TAIL_COVERAGE", "HIGH_TOKEN_RATIO",
    }
    # 차단 게이트가 아니다 — 모든 위반은 warning.
    assert all(f.severity == "warning" for f in report.findings)


def test_invalid_threshold_value_is_reported_not_crashed():
    report = CoverageAuditor().measure(
        {"P_0001": "a"}, [], "", thresholds={"min_token_ratio": "abc"},
    )
    assert any(f.code == "INVALID_COVERAGE_THRESHOLD" for f in report.findings)


@pytest.mark.anyio
async def test_router_ontology_run_writes_coverage_artifact(tmp_path):
    doc = "\n\n".join(
        f"Paragraph number {i} with several words of real content inside."
        for i in range(1, 7)
    )
    runs_base = tmp_path / "runs"
    router = OmniSupervisorRouter(use_mock=True, runs_base=str(runs_base))
    await router.route(RouterRequest(
        query=doc,
        lens="general",
        target_module=ModuleType.ONTOLOGY,
        use_mock=True,
    ))

    manifests = list(runs_base.rglob("manifest.json"))
    assert len(manifests) == 1
    run_out = manifests[0].parent
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))

    assert (run_out / "coverage.json").is_file()
    assert "coverage.json" in manifest["artifacts"]
    coverage = json.loads((run_out / "coverage.json").read_text(encoding="utf-8"))
    assert coverage["paragraph_count"] == 6
    # MockProvider는 앞 3개 문단만 앵커 → 후반 편식이 tail 지표로 드러난다.
    assert coverage["covered_paragraph_count"] == 3
    assert coverage["tail_coverage"] == 0.0
    assert manifest["paragraph_coverage"] == coverage["paragraph_coverage"]
    assert manifest["tail_coverage"] == coverage["tail_coverage"]
    assert manifest["token_ratio"] == coverage["token_ratio"]
    report_md = (run_out / "report.md").read_text(encoding="utf-8")
    assert "Coverage (Token-Ratio Defense)" in report_md
