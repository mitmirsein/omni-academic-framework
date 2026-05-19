import argparse
import asyncio
import os
from enum import Enum
from pathlib import Path

from pydantic import BaseModel
from rich.console import Console

from src.store.run_store import RunStore, export_to_vault

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
    forensic: bool = False
    export_vault: bool = False
    vault_path: str = ""
    no_cache: bool = False
    snowball: str = ""


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
    from src.llm.provider import AnthropicProvider
    return AnthropicProvider(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


class OmniSupervisorRouter:
    """단일 진입점 라우터 (Simple & Soft Architecture)."""

    def __init__(self, use_mock: bool = False):
        self.console = console
        self.use_mock = use_mock
        self._last_ontology = None

    async def route(self, request: RouterRequest):
        self.console.print("[bold blue]Omni-Academic Supervisor[/bold blue] 🚀")
        self.console.print(f"Lens 장착: [yellow]{request.lens}[/yellow]")
        self.use_mock = request.use_mock

        if request.target_module == ModuleType.ANALYZE:
            self._run_analyze(_resolve_document(request.query), request.lens)
            return

        store = RunStore.create(request.query, request.lens, mock=request.use_mock)
        try:
            if request.target_module == ModuleType.RECON:
                await self._run_recon(
                    store, request.query, request.lens,
                    forensic=request.forensic, no_cache=request.no_cache,
                    snowball=request.snowball,
                )
            elif request.target_module == ModuleType.ONTOLOGY:
                self._run_ontology(store, _resolve_document(request.query))
        finally:
            run_dir = store.finalize()
            self.console.print(f"\n[bold]💾 산출물 저장:[/bold] {run_dir}")

        if request.export_vault:
            try:
                out = export_to_vault(
                    store, request.vault_path, ontology=self._last_ontology
                )
                self.console.print(f"[bold green]📤 볼트 export:[/bold green] {out}")
            except ValueError as e:
                self.console.print(f"[bold yellow]볼트 export 생략: {e}[/bold yellow]")

    async def _run_recon(self, store: RunStore, query: str, lens: str,
                          forensic: bool = False, no_cache: bool = False,
                          snowball: str = ""):
        from rich.prompt import Prompt

        from src.recon.engine import CitationGraphClient, ReconEngine
        from src.recon.scraper import JinaReaderScraper, ScraperFactory

        engine = ReconEngine(use_cache=not no_cache)
        if snowball:
            self.console.print(
                f"[bold magenta]🕸️ Snowball 모드 (seed DOI: {snowball})[/bold magenta]"
            )
            papers = await CitationGraphClient().snowball(snowball)
            store.note("mode", "snowball")
            store.note("seed_doi", snowball)
        else:
            papers = await engine.search(query, lens=lens)
        if forensic and papers:
            from src.audit.forensic import ForensicAuditor
            findings = await ForensicAuditor().verify_papers(papers)
            store.write_forensic(findings)
            fpassed = ForensicAuditor.passed(findings)
            blocked = ForensicAuditor.failed_indices(findings)
            store.note("forensic_passed", fpassed)
            store.note("forensic_blocked_count", len(blocked))
            store.note("forensic_checked_count", len(papers))
            if blocked:
                self.console.print(
                    f"[bold red]🛡️ Gate 2: 유령 인용/가짜 DOI {len(blocked)}건 "
                    f"HITL 후보에서 차단[/bold red]"
                )
                papers = [p for i, p in enumerate(papers) if i not in blocked]

        engine.generate_digest(papers)
        store.write_digest(papers)
        store.note("recon_cache", engine.cache_report)

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
            # Content-Type 우선 판별(확장자 없는 PDF: arXiv /pdf/, doi 리다이렉트)
            scraper = await ScraperFactory.detect(target_paper.url)
        except ValueError as e:
            self.console.print(f"[bold red]스크래퍼 선택 불가: {e}[/bold red]")
            return

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

        store.write_fulltext(markdown_text)
        self.console.print("[bold green]원문 징발 성공! Ontology Extractor로 전달합니다...[/bold green]\n")
        self._run_ontology(store, markdown_text)

    def _run_ontology(self, store: RunStore, target_document: str):
        from src.audit.gate import AuditGate
        from src.ontology.extractor import OntologyExtractor
        from src.text.paragraphs import assign_paragraph_ids

        annotated, manifest = assign_paragraph_ids(target_document)
        store.write_paragraphs(manifest)

        try:
            extractor = OntologyExtractor(llm_provider=_make_provider(self.use_mock))
            ontology_map = extractor.extract(annotated)
        except (ValueError, NotImplementedError, RuntimeError) as e:
            self.console.print(f"[bold red]Ontology 추출 불가: {e}[/bold red]")
            return

        self._last_ontology = ontology_map
        store.write_ontology(ontology_map)
        self.console.print("\n[bold green]✅ Ontology Map Generation Complete![/bold green]")

        report = AuditGate().verify_ontology(ontology_map, paragraph_manifest=manifest)
        store.write_audit(report)
        if report.passed:
            self.console.print_json(ontology_map.model_dump_json())
        else:
            self.console.print(
                "[bold red]⚠️ Audit Gate에서 반려되었습니다. (Fail-Fast 발동)[/bold red]"
            )

    def _run_analyze(self, target_document: str, lens: str):
        from src.analyze.lens_analyzer import LensAnalyzer

        LensAnalyzer().analyze(target_document, lens)
        self.console.print(
            "   => [bold yellow]렌즈 스펙 프리뷰 완료 (실 분석은 BLUEPRINT)[/bold yellow]"
        )


def main():
    parser = argparse.ArgumentParser(description="Omni-Academic Supervisor Router")
    parser.add_argument(
        "query", type=str, nargs="?", default="",
        help="검색 쿼리 또는 타겟 문서 파일 경로 (생략 시 시스템 진단/셋업 화면 표출)"
    )
    parser.add_argument("--lens", type=str, default="general", help="장착할 도메인 렌즈 (예: cs, medical)")
    parser.add_argument(
        "--module", type=str, choices=["recon", "ontology", "analyze"],
        default="recon", help="가동할 타겟 모듈",
    )
    parser.add_argument(
        "--mock", action="store_true",
        help="LLM 호출 없이 MockProvider로 오프라인 실행 (테스트 전용)",
    )
    parser.add_argument(
        "--forensic", action="store_true",
        help="recon 결과에 Gate 2 ForensicAuditor(DOI/URL 실존 ping) 적용",
    )
    parser.add_argument(
        "--export-vault", action="store_true",
        help="audit 통과·non-mock 산출물을 볼트 Inbox/Drafts에 Markdown draft로 export",
    )
    parser.add_argument(
        "--vault-path", type=str, default=os.environ.get("ACADEMIC_VAULT_PATH", ""),
        help="볼트 루트 경로 (미지정 시 ACADEMIC_VAULT_PATH 환경변수). 추측하지 않음",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="ReconCache 바이패스(항상 fresh 호출). 캐시 적중은 manifest에 기록됨",
    )
    parser.add_argument(
        "--snowball", type=str, default="",
        help="키워드 검색 대신 seed DOI의 인용 네트워크 정찰(OpenAlex)",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="현재 시스템 설정 및 API Key 등 로컬 진단/셋업 화면을 출력",
    )
    parser.add_argument(
        "--setup", action="store_true",
        help="대화형 CLI 마법사를 통해 API Key 및 로컬 환경변수(.env) 설정",
    )
    args = parser.parse_args()

    if args.setup:
        from src.supervisor.status import run_setup_wizard
        run_setup_wizard()
        return

    if args.status or not args.query:
        from src.supervisor.status import run_diagnostics
        run_diagnostics()
        return

    request = RouterRequest(
        query=args.query,
        lens=args.lens,
        target_module=ModuleType(args.module),
        use_mock=args.mock,
        forensic=args.forensic,
        export_vault=args.export_vault,
        vault_path=args.vault_path,
        no_cache=args.no_cache,
        snowball=args.snowball,
    )

    asyncio.run(OmniSupervisorRouter(use_mock=args.mock).route(request))


if __name__ == "__main__":
    main()
