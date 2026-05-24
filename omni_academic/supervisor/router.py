import argparse
import asyncio
import json
import os
from enum import Enum
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pydantic import BaseModel
from rich.console import Console

from omni_academic.store.run_store import RunStore, verify_artifact_manifest
from omni_academic.supervisor import run_status

console = Console()


class ModuleType(str, Enum):
    RECON = "recon"
    ONTOLOGY = "ontology"
    ANALYZE = "analyze"
    DRAFT = "draft"
    REVIEW = "review"


class RouterRequest(BaseModel):
    query: str
    lens: str = "general"
    target_module: ModuleType
    use_mock: bool = False
    forensic: bool = False
    no_cache: bool = False
    snowball: str = ""
    kci_harvest: str = ""
    llm_analysis: bool = False
    llm_critic: bool = False


async def _probe_url(url: str) -> dict:
    """실패 진단용 best-effort HEAD: HTTP status·content-type만 수집."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as c:
            r = await c.head(url)
            return {
                "http_status": r.status_code,
                "content_type": r.headers.get("content-type"),
                "final_url": str(r.url),
            }
    except Exception as e:  # noqa: BLE001 — 진단 경로, 모든 실패를 기록만
        return {"http_status": None, "content_type": None, "probe_error": str(e)}


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
        from omni_academic.llm.provider import MockProvider
        return MockProvider()
    from omni_academic.llm.provider import AnthropicProvider
    return AnthropicProvider(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


def _lens_ontology_directive(lens: str) -> str:
    """렌즈의 도메인 온톨로지 지시(예: 신학 아포리아 보존)를 best-effort 로드.

    렌즈가 없거나 directive가 없으면 빈 문자열 → 코어는 도메인-중립 기본 동작.
    """
    from omni_academic.config.lens import (
        LensNotFoundError,
        get_ontology_directive,
        load_lens,
    )

    try:
        return get_ontology_directive(load_lens(lens))
    except LensNotFoundError:
        return ""


def _list_lenses(lens_dir: str = "lenses") -> list[dict]:
    from omni_academic.config.lens import (
        get_recon_client_names,
        load_lens,
        resolve_lens_dir,
    )

    root = Path(resolve_lens_dir(lens_dir))
    rows = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*.yaml")):
        try:
            cfg = load_lens(path.stem, lens_dir)
        except Exception:
            continue
        rows.append({
            "id": path.stem,
            "name": cfg.get("name", path.stem),
            "clients": get_recon_client_names(cfg),
            "focus": cfg.get("focus_areas", []) or [],
        })
    return rows


def _print_lenses(lens_dir: str = "lenses") -> None:
    from rich.table import Table

    table = Table(title="Available Lenses")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Recon Clients")
    table.add_column("Focus Areas")
    for row in _list_lenses(lens_dir):
        table.add_row(
            row["id"],
            str(row["name"]),
            ", ".join(row["clients"]) or "-",
            "; ".join(str(v) for v in row["focus"]) or "-",
        )
    console.print(table)


def _resolve_run_dir(run_ref: str, base: str = "runs") -> Path:
    base_path = Path(base)
    ref = (run_ref or "").strip()
    if not ref:
        raise ValueError("run ref가 비어 있습니다.")
    direct = Path(ref)
    candidates = [direct]
    candidates.extend([
        base_path / ref,
        base_path / ref / "latest",
    ])
    if "/" not in ref:
        candidates.extend(sorted(base_path.glob(f"{ref}/*"), reverse=True))
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved.is_dir() and (resolved / "manifest.json").is_file():
            return resolved
    raise ValueError(f"run을 찾을 수 없습니다: {run_ref}")


def _show_run(run_ref: str, base: str = "runs") -> None:
    run_dir = _resolve_run_dir(run_ref, base)
    manifest_path = run_dir / "manifest.json"
    report_path = run_dir / "report.md"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    console.print(f"[bold cyan]Run:[/bold cyan] {manifest.get('run_id')}")
    console.print(f"- Status: `{manifest.get('status', 'unknown')}`")
    console.print(f"- Query: {manifest.get('query')}")
    console.print(f"- Lens: `{manifest.get('lens')}`")
    console.print(f"- Mock: `{manifest.get('mock')}`")
    console.print(f"- Audit Passed: `{manifest.get('audit_passed')}`")
    if "forensic_passed" in manifest:
        console.print(f"- Forensic Passed: `{manifest.get('forensic_passed')}`")
    console.print(f"- Directory: `{run_dir}`")
    console.print(f"- Manifest: `{manifest_path}`")
    console.print(f"- Report: `{report_path}`")
    artifacts = manifest.get("artifacts") or []
    if artifacts:
        console.print("- Artifacts: " + ", ".join(f"`{a}`" for a in artifacts))
    artifact_manifest = manifest.get("artifact_manifest") or {}
    if artifact_manifest:
        ok = sum(1 for item in artifact_manifest.values() if item.get("exists"))
        total_bytes = sum(int(item.get("bytes") or 0) for item in artifact_manifest.values())
        console.print(
            f"- Artifact Integrity: `{ok}/{len(artifact_manifest)} present`, "
            f"`{total_bytes}` bytes"
        )


def _verify_run(run_ref: str, base: str = "runs") -> tuple[bool, list[str]]:
    run_dir = _resolve_run_dir(run_ref, base)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_manifest = manifest.get("artifact_manifest") or {}
    if not artifact_manifest:
        return False, ["manifest에 artifact_manifest가 없습니다."]

    issues = verify_artifact_manifest(run_dir, artifact_manifest)
    return not issues, issues


def _print_verify_run(run_ref: str, base: str = "runs") -> bool:
    ok, issues = _verify_run(run_ref, base)
    if ok:
        console.print(f"[bold green]✅ Run artifact integrity OK:[/bold green] {run_ref}")
    else:
        console.print(f"[bold red]❌ Run artifact integrity FAILED:[/bold red] {run_ref}")
        for issue in issues:
            console.print(f"- {issue}")
    return ok


class OmniSupervisorRouter:
    """단일 진입점 라우터 (Simple & Soft Architecture)."""

    def __init__(self, use_mock: bool = False, runs_base: str = "runs"):
        self.console = console
        self.use_mock = use_mock
        self.runs_base = runs_base
        self._last_ontology = None

    async def route(self, request: RouterRequest):
        self.console.print("[bold blue]Omni-Academic Supervisor[/bold blue] 🚀")
        self.console.print(f"Lens 장착: [yellow]{request.lens}[/yellow]")
        self.use_mock = request.use_mock

        store = RunStore.create(
            request.query,
            request.lens,
            mock=request.use_mock,
            base=self.runs_base,
        )
        store.note("status", run_status.RUNNING)
        try:
            if request.target_module == ModuleType.RECON:
                await self._run_recon(
                    store, request.query, request.lens,
                    forensic=request.forensic, no_cache=request.no_cache,
                    snowball=request.snowball, kci_harvest=request.kci_harvest,
                )
            elif request.target_module == ModuleType.ONTOLOGY:
                self._run_ontology(store, _resolve_document(request.query), request.lens)
            elif request.target_module == ModuleType.ANALYZE:
                self._run_analyze(
                    store,
                    _resolve_document(request.query),
                    request.lens,
                    llm_analysis=request.llm_analysis,
                    llm_critic=request.llm_critic,
                )
            elif request.target_module == ModuleType.DRAFT:
                self._run_draft(store, _resolve_document(request.query), request.lens)
            elif request.target_module == ModuleType.REVIEW:
                self._run_review(store, request.query, request.lens)
            if store._meta.get("status") == run_status.RUNNING:
                store.note("status", run_status.COMPLETED)
        except Exception as e:
            store.note("status", run_status.FAILED)
            store.note("error_message", str(e))
            self.console.print(f"\n[bold red]🚨 Supervisor 실행 중 에러 발생: {e}[/bold red]")
            raise e
        finally:
            run_dir = store.finalize()
            self.console.print(f"\n[bold]💾 산출물 저장:[/bold] {run_dir}")

    async def _run_recon(self, store: RunStore, query: str, lens: str,
                          forensic: bool = False, no_cache: bool = False,
                          snowball: str = "", kci_harvest: str = ""):
        from rich.prompt import Prompt

        from omni_academic.recon.engine import CitationGraphClient, KciOaiClient, ReconEngine
        from omni_academic.recon.scraper import JinaReaderScraper, ScraperFactory

        engine = ReconEngine(use_cache=not no_cache)
        if kci_harvest:
            self.console.print(
                f"[bold magenta]📚 KCI OAI-PMH 수확 모드 (set: {kci_harvest})[/bold magenta]"
            )
            papers = await KciOaiClient().harvest(kci_harvest)
            store.note("mode", "kci_oai_harvest")
            store.note("kci_set", kci_harvest)
        elif snowball:
            self.console.print(
                f"[bold magenta]🕸️ Snowball 모드 (seed DOI: {snowball})[/bold magenta]"
            )
            papers = await CitationGraphClient().snowball(snowball)
            store.note("mode", "snowball")
            store.note("seed_doi", snowball)
        else:
            papers = await engine.search(query, lens=lens)
        if forensic and papers:
            from omni_academic.audit.forensic import ForensicAuditor
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
            store.note("status", run_status.NO_PAPERS_FOUND)
            self.console.print("[bold red]검색된 논문이 없습니다. 정찰을 종료합니다.[/bold red]")
            return

        choice = Prompt.ask("\n[bold cyan]딥다이브할 논문 번호를 승인해 주십시오 (종료: q)[/bold cyan]")
        if choice.lower() == 'q' or not choice.isdigit():
            store.note("status", run_status.CANCELLED_BY_USER)
            self.console.print("정찰 모듈을 종료합니다.")
            return

        idx = int(choice) - 1
        if not (0 <= idx < len(papers)):
            store.note("status", run_status.INVALID_CHOICE)
            self.console.print("[bold red]잘못된 번호입니다.[/bold red]")
            return

        target_paper = papers[idx]
        self.console.print(f"\n[bold magenta]HITL 승인됨: [{target_paper.title}][/bold magenta]")
        self.console.print(f"URL: {target_paper.url}")

        try:
            # Content-Type 우선 판별(확장자 없는 PDF: arXiv /pdf/, doi 리다이렉트)
            scraper = await ScraperFactory.detect(target_paper.url)
        except ValueError as e:
            store.note("status", run_status.SCRAPER_DETECTION_FAILED)
            store.note("error_message", str(e))
            store.write_failure_artifact({
                "stage": "scraper_detection",
                "url": target_paper.url,
                "scraper": None,
                "error_message": str(e),
                **(await _probe_url(target_paper.url or "")),
            })
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
            store.note("status", run_status.SCRAPING_FAILED)
            store.write_failure_artifact({
                "stage": "scraping",
                "url": target_paper.url,
                "scraper": type(scraper).__name__,
                "error_message": "scraper returned empty markdown",
                **(await _probe_url(target_paper.url or "")),
            })
            self.console.print("[bold red]원문 스크래핑에 실패했습니다.[/bold red]")
            return

        store.write_fulltext(markdown_text)
        self.console.print("[bold green]원문 징발 성공! Ontology Extractor로 전달합니다...[/bold green]\n")
        self._run_ontology(store, markdown_text, lens)

    def _run_ontology(self, store: RunStore, target_document: str, lens: str = "general"):
        from omni_academic.audit.gate import AuditGate
        from omni_academic.ontology.extractor import OntologyExtractor
        from omni_academic.text.paragraphs import assign_paragraph_ids

        annotated, manifest = assign_paragraph_ids(target_document)
        store.write_paragraphs(manifest)

        try:
            extractor = OntologyExtractor(llm_provider=_make_provider(self.use_mock))
            ontology_map = extractor.extract(
                annotated, directive=_lens_ontology_directive(lens)
            )
        except (ValueError, NotImplementedError, RuntimeError) as e:
            store.note("status", run_status.ANALYSIS_FAILED)
            store.note("error_message", str(e))
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
            store.note("status", run_status.BLOCKED_BY_AUDIT)
            self.console.print(
                "[bold red]⚠️ Audit Gate에서 반려되었습니다. (Fail-Fast 발동)[/bold red]"
            )

    def _run_analyze(
        self,
        store: RunStore,
        target_document: str,
        lens: str,
        *,
        llm_analysis: bool = False,
        llm_critic: bool = False,
    ):
        from omni_academic.analyze.lens_analyzer import LensAnalyzer
        from omni_academic.audit.lens_gate import LensComplianceAuditor
        from omni_academic.config.lens import LensNotFoundError

        analyzer = LensAnalyzer()
        self.console.print(
            f"\n[bold magenta]🎯 [Lens Briefing Scaffold] (렌즈: {lens})[/bold magenta]"
        )
        try:
            brief = analyzer.build_brief(target_document, lens)
        except LensNotFoundError as e:
            store.note("status", run_status.ANALYSIS_FAILED)
            self.console.print(f"[bold red]❌ Error: {e}[/bold red]")
            return

        analyzer.print_brief(brief)
        store.write_lens_brief(brief)
        if llm_analysis:
            provider = _make_provider(self.use_mock)
            report = analyzer.build_llm_analysis(target_document, lens, provider)
            store.note("llm_usage", {
                "analysis": provider.last_usage,
                "analysis_attempts": analyzer.last_attempts,
            })
            store.write_lens_analysis(report, analyzer.render_analysis(report))
            lens_audit = LensComplianceAuditor().verify(report, target_document, lens)
            store.write_lens_audit(lens_audit)
            self.console.print(
                "   => [bold green]LLM lens analysis 저장 완료: "
                "lens_analysis.json, lens_analysis.md[/bold green]"
            )
            if lens_audit.passed:
                self.console.print(
                    f"   => [bold green]Gate 3 Lens Compliance 통과 "
                    f"(Score: {lens_audit.score}/100)[/bold green]"
                )
            else:
                self.console.print(
                    f"   => [bold red]Gate 3 Lens Compliance 반려 "
                    f"(Score: {lens_audit.score}/100)[/bold red]"
                )
            if llm_critic:
                critic_provider = _make_provider(self.use_mock)
                critic = analyzer.build_llm_critic(
                    target_document, lens, report, critic_provider,
                )
                usage = store._meta.get("llm_usage") or {}
                usage["critic"] = critic_provider.last_usage
                store.note("llm_usage", usage)
                critic_audit = LensComplianceAuditor().verify_critic(
                    critic, target_document
                )
                store.write_lens_critic(
                    critic,
                    analyzer.render_critic(critic),
                    critic_audit,
                )
                self.console.print(
                    "   => [bold green]LLM critic 저장 완료: "
                    "lens_critic.json, lens_critic.md[/bold green]"
                )
                if critic.passed and critic_audit.passed:
                    self.console.print("   => [bold green]LLM critic 통과[/bold green]")
                else:
                    self.console.print("   => [bold red]LLM critic 반려[/bold red]")
        if llm_analysis:
            self.console.print(
                "   => [bold yellow]렌즈 brief 저장 완료: lens_brief.md[/bold yellow]"
            )
        else:
            self.console.print(
                "   => [bold yellow]렌즈 brief 저장 완료: lens_brief.md "
                "(LLM 분석은 --llm-analysis 필요)[/bold yellow]"
            )

    def _run_draft(self, store: RunStore, target_document: str, lens: str):
        from omni_academic.audit.draft_gate import DraftComplianceAuditor
        from omni_academic.audit.gate import AuditGate
        from omni_academic.config.lens import LensNotFoundError
        from omni_academic.draft.scribe import ScribeAgent
        from omni_academic.ontology.extractor import OntologyExtractor
        from omni_academic.text.paragraphs import assign_paragraph_ids

        self.console.print(
            f"\n[bold magenta]✍️ [Drafting Module] (렌즈: {lens})[/bold magenta]"
        )
        annotated, manifest = assign_paragraph_ids(target_document)
        store.write_paragraphs(manifest)

        # 1) 온톨로지 추출 (초안의 근거 골격)
        try:
            ontology_map = OntologyExtractor(
                llm_provider=_make_provider(self.use_mock)
            ).extract(annotated, directive=_lens_ontology_directive(lens))
        except (ValueError, NotImplementedError, RuntimeError) as e:
            store.note("status", run_status.ANALYSIS_FAILED)
            self.console.print(f"[bold red]Ontology 추출 불가: {e}[/bold red]")
            return
        self._last_ontology = ontology_map
        store.write_ontology(ontology_map)
        ontology_audit = AuditGate().verify_ontology(
            ontology_map, paragraph_manifest=manifest
        )
        store.write_audit(ontology_audit)
        if not ontology_audit.passed:
            store.note("status", run_status.BLOCKED_BY_AUDIT)
            store.note("draft_blocked_by_audit", True)
            self.console.print(
                "   => [bold red]Draft skipped because ontology audit failed.[/bold red]"
            )
            return

        # 2) ScribeAgent 집필 (grounding 재시도 루프)
        scribe = ScribeAgent()
        provider = _make_provider(self.use_mock)
        try:
            draft = scribe.build_draft(target_document, ontology_map, lens, provider)
        except LensNotFoundError as e:
            store.note("status", run_status.ANALYSIS_FAILED)
            self.console.print(f"[bold red]❌ Error: {e}[/bold red]")
            return
        store.note("llm_usage", {
            "draft": provider.last_usage,
            "draft_attempts": scribe.last_attempts,
        })
        store.write_draft(draft, scribe.render_draft(draft))

        # 3) Draft Compliance Gate (claims ledger 결정론적 감사)
        draft_audit = DraftComplianceAuditor().verify(
            draft, target_document, ontology_map
        )
        store.write_draft_audit(draft_audit)
        if draft_audit.passed:
            self.console.print(
                f"   => [bold green]Draft Compliance 통과 "
                f"(Score: {draft_audit.score}/100) → draft.json, draft.md[/bold green]"
            )
        else:
            store.note("status", run_status.BLOCKED_BY_DRAFT_AUDIT)
            self.console.print(
                f"   => [bold red]Draft Compliance 반려 "
                f"(Score: {draft_audit.score}/100)[/bold red]"
            )

    def _run_review(self, store: RunStore, ref: str, lens: str):
        from omni_academic.analyze.peer_review import PeerReviewPanel
        from omni_academic.draft.scribe import DraftReport

        self.console.print(
            f"\n[bold magenta]👥 [Peer Review Panel] (렌즈: {lens})[/bold magenta]"
        )

        try:
            run_dir = _resolve_run_dir(ref, base=self.runs_base)
            draft_path = run_dir / "draft.json"
        except ValueError:
            p = Path(ref)
            if p.is_file():
                draft_path = p
            else:
                raise ValueError(f"리뷰 대상을 찾을 수 없습니다: {ref}")

        if not draft_path.is_file():
            raise FileNotFoundError(f"draft.json이 없습니다: {draft_path}")

        draft = DraftReport.model_validate_json(draft_path.read_text(encoding="utf-8"))

        panel = PeerReviewPanel()
        provider = _make_provider(self.use_mock)

        try:
            report = panel.build_review(draft, lens, provider)
        except ValueError as e:
            store.note("status", run_status.BLOCKED_BY_REVIEW_GROUNDING)
            store.note("review_grounding_passed", False)
            store.note("review_passed", False)
            store.note("llm_usage", {
                "review": provider.last_usage,
                "review_attempts": panel.last_attempts,
            })
            store.note("error_message", str(e))
            store.write_failure_artifact({
                "stage": "peer_review_grounding",
                "error_message": str(e),
                "review_attempts": panel.last_attempts,
            })
            self.console.print(
                f"   => [bold red]Peer Review grounding 반려: {e}[/bold red]"
            )
            return

        store.note("llm_usage", {
            "review": provider.last_usage,
            "review_attempts": panel.last_attempts,
        })
        store.note("review_grounding_passed", True)
        store.write_review(report, panel.render_review(report))

        if report.editor_decision in ("Accept", "Major Revision"):
            self.console.print(
                f"   => [bold green]Peer Review 통과 "
                f"(Decision: {report.editor_decision}, Score: {report.final_score}/100) → review.json, review.md[/bold green]"
            )
        else:
            store.note("status", run_status.REVIEW_REJECTED)
            self.console.print(
                f"   => [bold red]Peer Review 반려 "
                f"(Decision: {report.editor_decision}, Score: {report.final_score}/100)[/bold red]"
            )


def main():
    parser = argparse.ArgumentParser(description="Omni-Academic Supervisor Router")
    parser.add_argument(
        "query", type=str, nargs="?", default="",
        help="검색 쿼리 또는 타겟 문서 파일 경로 (생략 시 시스템 진단/셋업 화면 표출)"
    )
    parser.add_argument("--lens", type=str, default="general", help="장착할 도메인 렌즈 (예: cs, medical)")
    parser.add_argument(
        "--module", type=str, choices=["recon", "ontology", "analyze", "draft", "review"],
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
        "--no-cache", action="store_true",
        help="ReconCache 바이패스(항상 fresh 호출). 캐시 적중은 manifest에 기록됨",
    )
    parser.add_argument(
        "--snowball", type=str, default="",
        help="키워드 검색 대신 seed DOI의 인용 네트워크 정찰(OpenAlex)",
    )
    parser.add_argument(
        "--kci-harvest", type=str, default="", choices=["", "ARTI", "ARTI_CONF", "JOUR"],
        help="키워드 검색 대신 KCI OAI-PMH(무키 표준) set 수확: ARTI|ARTI_CONF|JOUR",
    )
    parser.add_argument(
        "--llm-analysis", action="store_true",
        help="analyze 모듈에서 source-bound LLM 분석 MVP를 추가 생성",
    )
    parser.add_argument(
        "--llm-critic", action="store_true",
        help="--llm-analysis 결과에 LLM self-redteaming critic pass를 추가 실행",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="현재 시스템 설정 및 API Key 등 로컬 진단/셋업 화면을 출력",
    )
    parser.add_argument(
        "--setup", action="store_true",
        help="대화형 CLI 마법사를 통해 API Key 및 로컬 환경변수(.env) 설정",
    )
    parser.add_argument(
        "--list-lenses", action="store_true",
        help="사용 가능한 렌즈와 recon client 목록을 출력",
    )
    parser.add_argument(
        "--show-run", type=str, default="",
        help="run id, query slug, 또는 run 디렉터리를 받아 manifest/report 위치를 출력",
    )
    parser.add_argument(
        "--verify-run", type=str, default="",
        help="run id, query slug, 또는 run 디렉터리의 artifact_manifest 무결성을 검증",
    )
    args = parser.parse_args()

    if args.setup:
        from omni_academic.supervisor.status import run_setup_wizard
        run_setup_wizard()
        return

    if args.list_lenses:
        _print_lenses()
        return

    if args.show_run:
        try:
            _show_run(args.show_run)
        except ValueError as e:
            console.print(f"[bold red]{e}[/bold red]")
        return

    if args.verify_run:
        try:
            ok = _print_verify_run(args.verify_run)
        except ValueError as e:
            console.print(f"[bold red]{e}[/bold red]")
            ok = False
        raise SystemExit(0 if ok else 1)

    if args.status or not args.query:
        from omni_academic.supervisor.status import run_diagnostics
        run_diagnostics()
        return

    request = RouterRequest(
        query=args.query,
        lens=args.lens,
        target_module=ModuleType(args.module),
        use_mock=args.mock,
        forensic=args.forensic,
        no_cache=args.no_cache,
        snowball=args.snowball,
        kci_harvest=args.kci_harvest,
        llm_analysis=args.llm_analysis or args.llm_critic,
        llm_critic=args.llm_critic,
    )

    asyncio.run(OmniSupervisorRouter(use_mock=args.mock).route(request))


if __name__ == "__main__":
    main()
