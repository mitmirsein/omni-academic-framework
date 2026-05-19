from typing import List
from pydantic import BaseModel
from rich.console import Console
from src.ontology.extractor import OntologyMap

console = Console()

class AuditReport(BaseModel):
    is_passed: bool
    score: int
    violations: List[str]

class AuditGate:
    """
    Omni-Academic Framework의 엄격한 품질 관리소.
    추출된 지식(Ontology)이나 분석 리포트가 논리적 결함(환각, 순환참조 등)을
    갖고 있지 않은지 기계적으로, 비판적으로 검열합니다.
    """
    def __init__(self):
        self.console = console

    def verify_ontology(self, ontology: OntologyMap) -> AuditReport:
        self.console.print("\n[bold red]🛡️ [Audit Gate] 가동... 온톨로지 무결성 검증을 시작합니다.[/bold red]")
        
        violations = []
        score = 100
        
        # 1. 고립 노드 (Orphan Nodes) 검사
        connected_node_ids = set()
        for edge in ontology.edges:
            connected_node_ids.add(edge.source_id)
            connected_node_ids.add(edge.target_id)
            
            # 2. 자기 참조 (Self-Loop) 검사
            if edge.source_id == edge.target_id:
                violations.append(f"Self-Loop Edge 감지: {edge.source_id} -> {edge.target_id}")
                score -= 20
                
            # 3. 빈약한 근거 (Reasoning) 검사
            if len(edge.reasoning) < 10:
                violations.append(f"Reasoning 빈약 감지: {edge.source_id}->{edge.target_id} ('{edge.reasoning}')")
                score -= 10

        for node in ontology.nodes:
            if node.id not in connected_node_ids:
                violations.append(f"고립 노드(Orphan Node) 감지: {node.label} ({node.id})")
                score -= 15
                
        # 80점 미만이면 Fail-Fast (Fail)
        is_passed = score >= 80
        
        report = AuditReport(is_passed=is_passed, score=score, violations=violations)
        self._print_report(report)
        return report

    def _print_report(self, report: AuditReport):
        if report.is_passed:
            self.console.print(f"[bold green]✅ Audit 통과 (Score: {report.score}/100)[/bold green]")
        else:
            self.console.print(f"[bold red]❌ Audit 실패 (Score: {report.score}/100) - Fail-Fast 발동![/bold red]")
            
        for v in report.violations:
            self.console.print(f"   ⚠️ {v}")
