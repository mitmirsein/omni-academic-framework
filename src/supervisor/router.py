import argparse
import asyncio
from enum import Enum
from pathlib import Path

from pydantic import BaseModel
from rich.console import Console

console = Console()


class ModuleType(str, Enum):
    RECON = "recon"
    ONTOLOGY = "ontology"
    ANALYZE = "analyze"


class RouterRequest(BaseModel):
    query: str
    lens: str = "general"
    target_module: ModuleType
    use_mock: bool = False


def _resolve_document(query: str) -> str:
    """query가 실존 파일 경로면 내용을 읽고, 아니면 인라인 텍스트로 취급."""
    path = Path(query)
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError as e:
        console.print(f"[bold red]파일 읽기 실패({query}): {e}[/bold red]")
    return query


def _make_provider(use_mock: bool):
    if use_mock:
        from src.llm.provider import MockProvider
        return MockProvider()
    import os

    from src.llm.provider import AnthropicProvider
    return AnthropicProvider(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


class OmniSupervisorRouter:
    """단일 진입점 라우터 (Simple & Soft Architecture)."""

    def __init__(self, use_mock: bool = False):
        self.console = console
        self.use_mock = use_mock

    async def route(self, request: RouterRequest):
        self.console.print("[bold blue]Omni-Academic Supervisor[/bold blue] 🚀")
        self.console.print(f"Lens 장착: [yellow]{request.lens}[/yellow]")
        self.use_mock = request.use_mock

        if request.target_module == ModuleType.RECON:
            await self._run_recon(request.query, request.lens)
        elif request.target_module == ModuleType.ONTOLOGY:
            self._run_ontology(_resolve_document(request.query))
        elif request.target_module == ModuleType.ANALYZE:
            self._run_analyze(_resolve_document(request.query), request.lens)
        else:
            self.console.print("[bold red]Unknown module requested.[/bold red]")

    async def _run_recon(self, query: str, lens: str):
        from rich.prompt import Prompt

        from src.recon.engine import ReconEngine
        from src.recon.scraper import ScraperFactory

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
        if not (0 <= idx < len(papers)):
            self.console.print("[bold red]잘못된 번호입니다.[/bold red]")
            return

        target_paper = papers[idx]
        self.console.print(f"\n[bold magenta]HITL 승인됨: [{target_paper.title}][/bold magenta]")
        self.console.print(f"URL: {target_paper.url}")

        try:
            scraper = ScraperFactory.get_scraper(target_paper.url)
        except ValueError as e:
            self.console.print(f"[bold red]스크래퍼 선택 불가: {e}[/bold red]")
            return

        from src.recon.scraper import JinaReaderScraper

        try:
            markdown_text = await scraper.fetch_markdown(target_paper.url)
        except NotImplementedError:
            self.console.print(
                "[yellow]선택된 스크래퍼가 BLUEPRINT 상태 → JinaReader 폴백 시도[/yellow]"
            )
            try:
                markdown_text = await JinaReaderScraper().fetch_markdown(target_paper.url)
            except NotImplementedError:
                markdown_text = ""
        if not markdown_text:
            self.console.print("[bold red]원문 스크래핑에 실패했습니다.[/bold red]")
            return

        self.console.print("[bold green]원문 징발 성공! Ontology Extractor로 전달합니다...[/bold green]\n")
        self._run_ontology(markdown_text)

    def _run_ontology(self, target_document: str):
        from src.audit.gate import AuditGate
        from src.ontology.extractor import OntologyExtractor
        from src.text.paragraphs import assign_paragraph_ids

        annotated, manifest = assign_paragraph_ids(target_document)

        try:
            extractor = OntologyExtractor(llm_provider=_make_provider(self.use_mock))
            ontology_map = extractor.extract(annotated)
        except (ValueError, NotImplementedError, RuntimeError) as e:
            self.console.print(f"[bold red]Ontology 추출 불가: {e}[/bold red]")
            return

        self.console.print("\n[bold green]✅ Ontology Map Generation Complete![/bold green]")

        report = AuditGate().verify_ontology(ontology_map, paragraph_manifest=manifest)
        if report.passed:
            self.console.print_json(ontology_map.model_dump_json())
        else:
            self.console.print(
                "[bold red]⚠️ Audit Gate에서 반려되었습니다. (Fail-Fast 발동)[/bold red]"
            )

    def _run_analyze(self, target_document: str, lens: str):
        from src.analyze.lens_analyzer import LensAnalyzer

        LensAnalyzer().analyze(target_document, lens)
        self.console.print("   => [bold green]최종 분석 리포트 도출 완료[/bold green]")


def main():
    parser = argparse.ArgumentParser(description="Omni-Academic Supervisor Router")
    parser.add_argument("query", type=str, help="검색 쿼리 또는 타겟 문서 파일 경로")
    parser.add_argument("--lens", type=str, default="general", help="장착할 도메인 렌즈 (예: cs, medical)")
    parser.add_argument(
        "--module", type=str, choices=["recon", "ontology", "analyze"],
        default="recon", help="가동할 타겟 모듈",
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="LLM 호출 없이 MockProvider로 오프라인 실행 (테스트 전용)",
    )
    args = parser.parse_args()

    request = RouterRequest(
        query=args.query,
        lens=args.lens,
        target_module=ModuleType(args.module),
        use_mock=args.mock,
    )

    asyncio.run(OmniSupervisorRouter(use_mock=args.mock).route(request))


if __name__ == "__main__":
    main()
