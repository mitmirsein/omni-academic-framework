import argparse
import sys
import asyncio
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

    async def route(self, request: RouterRequest):
        self.console.print(f"[bold blue]Omni-Academic Supervisor[/bold blue] 🚀")
        self.console.print(f"Lens 장착: [yellow]{request.lens}[/yellow]")
        
        if request.target_module == ModuleType.RECON:
            await self._run_recon(request.query, request.lens)
        elif request.target_module == ModuleType.ONTOLOGY:
            await self._run_ontology(request.query)
        elif request.target_module == ModuleType.ANALYZE:
            await self._run_analyze(request.query, request.lens)
        else:
            self.console.print("[bold red]Unknown module requested.[/bold red]")

    async def _run_recon(self, query: str, lens: str):
        from src.recon.engine import ReconEngine
        from src.recon.scraper import ScraperFactory
        from rich.prompt import Prompt
        
        engine = ReconEngine()
        papers = await engine.search(query, lens=lens)
        engine.generate_digest(papers)
        
        if not papers:
            self.console.print("[bold red]검색된 논문이 없습니다. 정찰을 종료합니다.[/bold red]")
            return
            
        choice = Prompt.ask("\n[bold cyan]딥다이브할 논문 번호를 승인해 주십시오 (종료: q)[/bold cyan]")
        
        if choice.lower() == 'q' or not choice.isdigit():
            self.console.print("정찰 모듈을 종료합니다.")
            return
            
        idx = int(choice) - 1
        if 0 <= idx < len(papers):
            target_paper = papers[idx]
            self.console.print(f"\n[bold magenta]HITL 승인됨: [{target_paper.title}][/bold magenta]")
            self.console.print(f"URL: {target_paper.url}")
            
            # Scraper 가동
            scraper = ScraperFactory.get_scraper(target_paper.url)
            markdown_text = await scraper.fetch_markdown(target_paper.url)
            
            if markdown_text:
                self.console.print("[bold green]원문 징발 성공! Ontology Extractor로 전달합니다...[/bold green]\n")
                # E2E 파이프라인 연결: 바로 온톨로지 추출로 넘김
                await self._run_ontology(markdown_text)
            else:
                self.console.print("[bold red]원문 스크래핑에 실패했습니다.[/bold red]")
        else:
            self.console.print("[bold red]잘못된 번호입니다.[/bold red]")

    async def _run_ontology(self, target_document: str):
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

    async def _run_analyze(self, target_document: str, lens: str):
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
    asyncio.run(router.route(request))

if __name__ == "__main__":
    main()
