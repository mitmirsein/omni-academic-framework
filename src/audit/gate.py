from datetime import datetime, timezone
from typing import List, Literal, Optional, Set

from pydantic import BaseModel
from rich.console import Console

from src.ontology.extractor import OntologyMap

console = Console()


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
        paragraph_manifest: Optional[Set[str]] = None,
    ) -> AuditReport:
        self.console.print(
            "\n[bold red]🛡️ [Audit Gate] 가동... 온톨로지 무결성 검증을 시작합니다.[/bold red]"
        )

        findings: List[AuditFinding] = []
        node_ids = {n.id for n in ontology.nodes}
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
