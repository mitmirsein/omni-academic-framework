import argparse
import sys
from rich.console import Console
from pydantic import BaseModel
from enum import Enum

console = Console()

class ModuleType(str, Enum):
    RECON = "recon"
    ONTOLOGY = "ontology"
    ANALYZE = "analyze"

class RouterRequest(BaseModel):
    query: str
    lens: str = "general"
    target_module: ModuleType

class OmniSupervisorRouter:
    """
    단일 진입점 라우터 (Simple & Soft Architecture)
    사용자의 요청을 받아 온디맨드로 적절한 모듈(Recon, Ontology, Analyze)에 분기합니다.
    """
    def __init__(self):
        self.console = console

    def route(self, request: RouterRequest):
        self.console.print(f"[bold blue]Omni-Academic Supervisor[/bold blue] 🚀")
        self.console.print(f"Lens 장착: [yellow]{request.lens}[/yellow]")
        
        if request.target_module == ModuleType.RECON:
            self._run_recon(request.query, request.lens)
        elif request.target_module == ModuleType.ONTOLOGY:
            self._run_ontology(request.query)
        elif request.target_module == ModuleType.ANALYZE:
            self._run_analyze(request.query, request.lens)
        else:
            self.console.print("[bold red]Unknown module requested.[/bold red]")

    def _run_recon(self, query: str, lens: str):
        from src.recon.engine import ReconEngine
        engine = ReconEngine()
        papers = engine.search(query, lens=lens)
        engine.generate_digest(papers)

    def _run_ontology(self, target_document: str):
        from src.ontology.extractor import OntologyExtractor
        from src.audit.gate import AuditGate
        
        extractor = OntologyExtractor()
        ontology_map = extractor.extract(target_document)
        
        self.console.print("\n[bold green]✅ Ontology Map Generation Complete![/bold green]")
        
        # 3중 무결성 검증 (Audit Gate)
        auditor = AuditGate()
        report = auditor.verify_ontology(ontology_map)
        
        if report.is_passed:
            self.console.print_json(ontology_map.model_dump_json())
        else:
            self.console.print("[bold red]⚠️ Audit Gate에서 반려되었습니다. (Fail-Fast 발동)[/bold red]")

    def _run_analyze(self, target_document: str, lens: str):
        from src.analyze.lens_analyzer import LensAnalyzer
        analyzer = LensAnalyzer()
        analyzer.analyze(target_document, lens)
        self.console.print("   => [bold green]최종 분석 리포트 도출 완료[/bold green]")

def main():
    parser = argparse.ArgumentParser(description="Omni-Academic Supervisor Router")
    parser.add_argument("query", type=str, help="검색 쿼리 또는 타겟 문서 경로")
    parser.add_argument("--lens", type=str, default="general", help="장착할 도메인 렌즈 (예: cs, med, theo)")
    parser.add_argument("--module", type=str, choices=["recon", "ontology", "analyze"], default="recon", help="가동할 타겟 모듈")
    
    args = parser.parse_args()
    
    request = RouterRequest(
        query=args.query,
        lens=args.lens,
        target_module=ModuleType(args.module)
    )
    
    router = OmniSupervisorRouter()
    router.route(request)

if __name__ == "__main__":
    main()
