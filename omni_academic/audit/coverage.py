"""헌법 §3 '토큰 비율 방어선' — 무손실 정량 지표 (결정론, LLM 불사용).

산출물이 원문 문단을 얼마나 앵커로 덮는지(paragraph/tail coverage),
원문 대비 어느 토큰 비율로 산출됐는지(token ratio)를 측정한다.

기본은 차단하지 않는 진단 계층이다: 임계값은 렌즈 YAML의
`coverage_thresholds` 필드로만 주입되며(헌법 §2 — 코어에 도메인별
임계값 하드코딩 금지), 위반은 warning finding으로 기록된다.
"""

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from pydantic import BaseModel, Field

from omni_academic.audit.gate import AuditFinding


def _token_count(text: str) -> int:
    return len((text or "").split())


class CoverageReport(BaseModel):
    paragraph_count: int
    covered_paragraph_count: int
    paragraph_coverage: float = Field(description="앵커된 문단 비율 (0..1)")
    tail_paragraph_count: int
    tail_covered_count: int
    tail_coverage: float = Field(
        description="문서 후반 1/3 구간의 문단 커버리지 — 앞부분 편식 검출용 (0..1)"
    )
    source_tokens: int
    output_tokens: int
    token_ratio: float = Field(description="원문 대비 산출물 토큰 비율")
    findings: List[AuditFinding] = Field(default_factory=list)
    checked_at: datetime


class CoverageAuditor:
    """원문 paragraph_map과 산출물 앵커/텍스트의 결정론적 대조."""

    # 렌즈 coverage_thresholds에서 지원하는 키 → (필드, 비교 방향, finding code)
    _THRESHOLD_RULES = (
        ("min_paragraph_coverage", "paragraph_coverage", "min", "LOW_PARAGRAPH_COVERAGE"),
        ("min_tail_coverage", "tail_coverage", "min", "LOW_TAIL_COVERAGE"),
        ("min_token_ratio", "token_ratio", "min", "LOW_TOKEN_RATIO"),
        ("max_token_ratio", "token_ratio", "max", "HIGH_TOKEN_RATIO"),
    )

    def measure(
        self,
        paragraph_map: Dict[str, str],
        anchored_ids: Iterable[str],
        output_text: str,
        thresholds: Optional[dict] = None,
    ) -> CoverageReport:
        pids = list(paragraph_map.keys())  # 삽입 순서 = 원문 순서 (P_0001..)
        anchored = {pid for pid in anchored_ids if pid in paragraph_map}
        count = len(pids)
        covered = len(anchored)
        tail_count = max(1, count // 3) if count else 0
        tail_ids = pids[-tail_count:] if tail_count else []
        tail_covered = sum(1 for pid in tail_ids if pid in anchored)
        source_tokens = sum(_token_count(text) for text in paragraph_map.values())
        output_tokens = _token_count(output_text)

        report = CoverageReport(
            paragraph_count=count,
            covered_paragraph_count=covered,
            paragraph_coverage=round(covered / count, 4) if count else 0.0,
            tail_paragraph_count=tail_count,
            tail_covered_count=tail_covered,
            tail_coverage=round(tail_covered / tail_count, 4) if tail_count else 0.0,
            source_tokens=source_tokens,
            output_tokens=output_tokens,
            token_ratio=(
                round(output_tokens / source_tokens, 4) if source_tokens else 0.0
            ),
            checked_at=datetime.now(timezone.utc),
        )
        report.findings = self._threshold_findings(report, thresholds or {})
        return report

    @classmethod
    def _threshold_findings(
        cls, report: CoverageReport, thresholds: dict
    ) -> List[AuditFinding]:
        findings: List[AuditFinding] = []
        for key, field, direction, code in cls._THRESHOLD_RULES:
            if key not in thresholds:
                continue
            try:
                limit = float(thresholds[key])
            except (TypeError, ValueError):
                findings.append(AuditFinding(
                    severity="warning", code="INVALID_COVERAGE_THRESHOLD",
                    message=f"렌즈 coverage_thresholds.{key} 값이 숫자가 아님: {thresholds[key]!r}",
                ))
                continue
            value = getattr(report, field)
            violated = value < limit if direction == "min" else value > limit
            if violated:
                findings.append(AuditFinding(
                    severity="warning", code=code,
                    message=(
                        f"{field}={value}가 렌즈 임계값({key}={limit})을 벗어남 — "
                        "원문 손실/편식 가능성 점검 필요"
                    ),
                ))
        return findings
