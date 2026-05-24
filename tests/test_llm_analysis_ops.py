from omni_academic.analyze.lens_analyzer import LensAnalysisReport, LensAnalyzer
from omni_academic.llm.provider import MockProvider

DOC = "Inflation targeting anchors expectations.\n\nBond yields decompose into risk premia."


class _ScriptedProvider:
    """첫 호출은 grounding 위반, 두 번째는 정상 — 재시도/수정 루프 검증용."""

    def __init__(self):
        self.calls = 0
        self.last_usage = None

    def generate_structured_output(self, prompt, schema):
        self.calls += 1
        self.last_usage = {"model": "scripted", "mock": False, "call": self.calls}
        if self.calls == 1:
            quote = "THIS QUOTE IS NOT IN ANY PARAGRAPH"
        else:
            quote = "Inflation targeting anchors expectations."
        return LensAnalysisReport(
            lens="general",
            executive_summary="s",
            findings=[{
                "focus_area": "Core",
                "paragraph_id": "P_0001",
                "source_quote": quote,
                "analysis": "a",
            }],
            limitations=[],
        )


class _AlwaysBadProvider(_ScriptedProvider):
    def generate_structured_output(self, prompt, schema):
        self.calls += 1
        self.last_usage = {"model": "bad", "call": self.calls}
        return LensAnalysisReport(
            lens="general", executive_summary="s",
            findings=[{
                "focus_area": "Core", "paragraph_id": "P_0001",
                "source_quote": "NEVER PRESENT", "analysis": "a",
            }],
            limitations=[],
        )


def test_retry_loop_self_corrects_grounding():
    az = LensAnalyzer()
    prov = _ScriptedProvider()
    report = az.build_llm_analysis(DOC, "general", prov, max_attempts=2)
    assert prov.calls == 2  # 1차 실패 → 교정 피드백 후 2차 성공
    assert az.last_attempts == 2
    assert report.findings[0].source_quote == "Inflation targeting anchors expectations."


def test_retry_loop_exhausts_without_crash():
    az = LensAnalyzer()
    prov = _AlwaysBadProvider()
    report = az.build_llm_analysis(DOC, "general", prov, max_attempts=2)
    # 크래시 대신 마지막 리포트 반환 → Gate 3가 결정론적으로 실패 기록
    assert prov.calls == 2
    assert az.last_attempts == 2
    assert report is not None


def test_mock_provider_stamps_usage_not_faking_real():
    prov = MockProvider()
    LensAnalyzer().build_llm_analysis(DOC, "general", prov)
    assert prov.last_usage["mock"] is True
    assert prov.last_usage["model"] == "mock"
