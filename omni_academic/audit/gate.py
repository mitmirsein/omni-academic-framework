from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, Set, Union

from pydantic import BaseModel
from rich.console import Console

from omni_academic.ontology.extractor import OntologyMap

console = Console()

MIN_QUOTE_CHARS = 8
MAX_QUOTE_CHARS = 200


def _canon(text: str) -> str:
    """인용 대조용 정규화: 소문자 + 공백 단일화."""
    return " ".join((text or "").lower().split())


def _quote_len(text: str) -> int:
    return len("".join((text or "").split()))


def _quote_quality_findings(
    *,
    quote: str,
    label: str,
    source_ref: Optional[str] = None,
) -> List["AuditFinding"]:
    findings: List[AuditFinding] = []
    qlen = _quote_len(quote)
    if qlen and qlen < MIN_QUOTE_CHARS:
        findings.append(AuditFinding(
            severity="warning", code="QUOTE_TOO_SHORT",
            message=f"source_quote가 너무 짧아 검증력이 약함: {label}",
            source_ref=source_ref,
        ))
    if qlen > MAX_QUOTE_CHARS:
        findings.append(AuditFinding(
            severity="warning", code="QUOTE_TOO_LONG",
            message=f"source_quote가 너무 길어 근거 범위가 흐림: {label}",
            source_ref=source_ref,
        ))
    return findings


class AuditFinding(BaseModel):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    source_ref: Optional[str] = None


class AuditReport(BaseModel):
    passed: bool
    score: int
    findings: List[AuditFinding]
    checked_at: datetime

    @property
    def is_passed(self) -> bool:  # 하위호환 alias
        return self.passed

    @property
    def violations(self) -> List[str]:  # 하위호환 alias
        return [f"[{f.code}] {f.message}" for f in self.findings]


class AuditGate:
    """기계적 대조 계층.

    핵심 검증은 'paragraph grounding': 모든 노드의 paragraph_id가 원문에서
    추출된 manifest에 실제로 존재해야 한다. manifest가 주어지지 않으면
    환각 검증이 불가능하므로 저신뢰(error)로 처리한다.
    """

    def __init__(self):
        self.console = console

    def verify_ontology(
        self,
        ontology: OntologyMap,
        paragraph_manifest: Optional[Union[Set[str], Dict[str, str]]] = None,
    ) -> AuditReport:
        self.console.print(
            "\n[bold red]🛡️ [Audit Gate] 가동... 온톨로지 무결성 검증을 시작합니다.[/bold red]"
        )

        findings: List[AuditFinding] = []
        node_ids = {n.id for n in ontology.nodes}
        node_by_id = {n.id: n for n in ontology.nodes}
        connected: Set[str] = set()

        for edge in ontology.edges:
            connected.add(edge.source_id)
            connected.add(edge.target_id)

            if edge.source_id == edge.target_id:
                findings.append(AuditFinding(
                    severity="error", code="SELF_LOOP",
                    message=f"자기 참조 엣지: {edge.source_id} -> {edge.target_id}",
                    source_ref=edge.source_id,
                ))
            for endpoint in (edge.source_id, edge.target_id):
                if endpoint not in node_ids:
                    findings.append(AuditFinding(
                        severity="error", code="DANGLING_EDGE",
                        message=f"존재하지 않는 노드를 가리키는 엣지: {endpoint}",
                        source_ref=endpoint,
                    ))
            if len(edge.reasoning.strip()) < 10:
                findings.append(AuditFinding(
                    severity="warning", code="WEAK_REASONING",
                    message=f"근거 빈약: {edge.source_id}->{edge.target_id} ('{edge.reasoning}')",
                ))

        for node in ontology.nodes:
            if node.id not in connected:
                findings.append(AuditFinding(
                    severity="warning", code="ORPHAN_NODE",
                    message=f"고립 노드: {node.label} ({node.id})",
                    source_ref=node.id,
                ))

        # --- 핵심: paragraph grounding (환각 차단) ---
        if paragraph_manifest is None:
            findings.append(AuditFinding(
                severity="error", code="NO_SOURCE_MANIFEST",
                message="원문 paragraph manifest 미제공 → 환각 검증 불가(저신뢰).",
            ))
        else:
            # dict면 문단 텍스트까지 보유 → source_quote in-paragraph 검사 가능.
            # set(레거시)면 paragraph_id 실존만 검사(quote 검사 생략).
            has_text = isinstance(paragraph_manifest, dict)
            corpus = (
                _canon(" ".join(paragraph_manifest.values())) if has_text else ""
            )
            for node in ontology.nodes:
                if node.paragraph_id not in paragraph_manifest:
                    findings.append(AuditFinding(
                        severity="error", code="UNGROUNDED_NODE",
                        message=(
                            f"원문에 없는 paragraph_id 참조(환각 의심): "
                            f"{node.label} -> {node.paragraph_id}"
                        ),
                        source_ref=node.id,
                    ))
                    continue
                if not has_text:
                    continue
                q = _canon(node.source_quote)
                if not q:
                    findings.append(AuditFinding(
                        severity="warning", code="MISSING_QUOTE",
                        message=f"source_quote 누락(검증 약화): {node.label}",
                        source_ref=node.id,
                    ))
                elif q not in _canon(paragraph_manifest[node.paragraph_id]):
                    findings.append(AuditFinding(
                        severity="error", code="UNGROUNDED_QUOTE",
                        message=(
                            f"인용이 해당 문단에 없음(환각): {node.label} "
                            f"-> {node.paragraph_id}"
                        ),
                        source_ref=node.id,
                    ))
                else:
                    findings.extend(_quote_quality_findings(
                        quote=node.source_quote,
                        label=node.label,
                        source_ref=node.id,
                    ))

            if has_text:
                node_quote_refs: Dict[str, List[str]] = {}
                for node in ontology.nodes:
                    q = _canon(node.source_quote)
                    if q:
                        node_quote_refs.setdefault(q, []).append(node.id)
                for refs in node_quote_refs.values():
                    if len(refs) > 1:
                        findings.append(AuditFinding(
                            severity="warning", code="DUPLICATE_NODE_QUOTE",
                            message=(
                                "여러 노드가 동일한 source_quote를 재사용함: "
                                + ", ".join(refs)
                            ),
                            source_ref=refs[0],
                        ))

                edge_quote_refs: Dict[str, List[str]] = {}
                for edge in ontology.edges:
                    q = _canon(edge.source_quote)
                    if not q:
                        findings.append(AuditFinding(
                            severity="warning", code="MISSING_QUOTE",
                            message=f"엣지 source_quote 누락: {edge.source_id}->{edge.target_id}",
                        ))
                    elif q not in corpus:
                        findings.append(AuditFinding(
                            severity="error", code="UNGROUNDED_QUOTE",
                            message=(
                                f"엣지 인용이 원문에 없음(환각): "
                                f"{edge.source_id}->{edge.target_id}"
                            ),
                        ))
                    else:
                        findings.extend(_quote_quality_findings(
                            quote=edge.source_quote,
                            label=f"{edge.source_id}->{edge.target_id}",
                        ))
                        edge_quote_refs.setdefault(q, []).append(
                            f"{edge.source_id}->{edge.target_id}"
                        )
                        endpoint_paragraphs = []
                        for node_id in (edge.source_id, edge.target_id):
                            node = node_by_id.get(node_id)
                            if node is not None and node.paragraph_id in paragraph_manifest:
                                endpoint_paragraphs.append(paragraph_manifest[node.paragraph_id])
                        endpoint_corpus = _canon(" ".join(endpoint_paragraphs))
                        if endpoint_corpus and q not in endpoint_corpus:
                            findings.append(AuditFinding(
                                severity="warning", code="DETACHED_EDGE_QUOTE",
                                message=(
                                    "엣지 source_quote가 전체 원문에는 있으나 "
                                    f"연결된 노드 문단에는 없음: {edge.source_id}->{edge.target_id}"
                                ),
                            ))
                for refs in edge_quote_refs.values():
                    if len(refs) > 1:
                        findings.append(AuditFinding(
                            severity="warning", code="DUPLICATE_EDGE_QUOTE",
                            message=(
                                "여러 엣지가 동일한 source_quote를 재사용함: "
                                + ", ".join(refs)
                            ),
                        ))

        penalty = sum(
            25 if f.severity == "error" else 10 if f.severity == "warning" else 0
            for f in findings
        )
        score = max(0, 100 - penalty)
        passed = not any(f.severity == "error" for f in findings)

        report = AuditReport(
            passed=passed,
            score=score,
            findings=findings,
            checked_at=datetime.now(timezone.utc),
        )
        self._print_report(report)
        return report

    def _print_report(self, report: AuditReport):
        if report.passed:
            self.console.print(
                f"[bold green]✅ Audit 통과 (Score: {report.score}/100)[/bold green]"
            )
        else:
            self.console.print(
                f"[bold red]❌ Audit 실패 (Score: {report.score}/100) - Fail-Fast 발동![/bold red]"
            )
        for f in report.findings:
            icon = "⛔" if f.severity == "error" else "⚠️" if f.severity == "warning" else "ℹ️"
            self.console.print(f"   {icon} [{f.code}] {f.message}")
