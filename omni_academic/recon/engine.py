"""Recon 오케스트레이션 엔진.

클라이언트 구현은 `omni_academic/recon/clients/` 패키지로 분리되었다
(plug-and-play, 헌법 §5). 기존 `from omni_academic.recon.engine import X`
경로는 아래 재수출로 그대로 동작한다.
"""

import asyncio
from typing import List

import httpx  # noqa: F401  — 기존 테스트가 engine_mod.httpx로 전역 httpx를 패치한다
from rich.console import Console
from rich.panel import Panel

from omni_academic.recon.clients import (
    CLIENT_FACTORY,
    ArxivClient,
    BaseAPIClient,
    CitationGraphClient,
    CrossrefClient,
    DBLPClient,
    EconBizClient,
    KCIClient,
    KciOaiClient,
    OpenAlexClient,
    PaperMetadata,
    PubMedClient,
    SemanticScholarClient,
    SerpApiScholarClient,
)
from omni_academic.recon.clients.base import _findtext, _norm  # noqa: F401 — 하위호환

console = Console()

__all__ = [
    "ArxivClient",
    "BaseAPIClient",
    "CLIENT_FACTORY",
    "CitationGraphClient",
    "CrossrefClient",
    "DBLPClient",
    "EconBizClient",
    "KCIClient",
    "KciOaiClient",
    "OpenAlexClient",
    "PaperMetadata",
    "PubMedClient",
    "ReconEngine",
    "SemanticScholarClient",
    "SerpApiScholarClient",
]


class ReconEngine:
    def __init__(self, lens_dir: str = "lenses", *, use_cache: bool = True,
                 cache_dir: str = ".cache"):
        self.console = console
        self.lens_dir = lens_dir
        self.use_cache = use_cache
        self._cache = None
        if use_cache:
            from omni_academic.store.recon_cache import ReconCache
            self._cache = ReconCache(base=cache_dir)
        # manifest 자기검증용 — client별 캐시 적중/나이 기록
        self.cache_report: dict = {}

    def _resolve_clients(self, lens: str) -> List[BaseAPIClient]:
        from omni_academic.config.lens import (
            DEFAULT_LENS,
            LensNotFoundError,
            get_recon_client_names,
            load_lens,
        )

        try:
            cfg = load_lens(lens, self.lens_dir)
        except LensNotFoundError:
            self.console.print(
                f"  [yellow]렌즈 '{lens}' 미존재 → '{DEFAULT_LENS}' 로 폴백[/yellow]"
            )
            cfg = load_lens(DEFAULT_LENS, self.lens_dir)

        names = get_recon_client_names(cfg) or ["crossref"]
        clients: List[BaseAPIClient] = []
        for n in names:
            factory = CLIENT_FACTORY.get(n)
            if factory is None:
                self.console.print(f"  [yellow]알 수 없는 recon 클라이언트 무시: {n}[/yellow]")
                continue
            clients.append(factory())
        return clients or [CrossrefClient()]

    async def search(self, query: str, lens: str = "general") -> List[PaperMetadata]:
        self.console.print(f"[bold cyan]🔍 비동기 Recon Engine 가동 중... (Lens: {lens})[/bold cyan]")

        clients = self._resolve_clients(lens)
        client_names = [type(c).__name__.replace("Client", "") for c in clients]
        self.console.print(f"  [bold]🚀 정찰 순서 (Recon Clients Sequence):[/bold] [yellow]{' -> '.join(client_names)}[/yellow]")
        self.cache_report = {}

        self.console.print("  - [italic]API 플러그인 병렬 스크래핑(Gathering) 시작...[/italic]")

        results: List[PaperMetadata] = []
        live: list = []  # (client, name) — 캐시 미스라 실제 호출할 대상

        for client in clients:
            name = type(client).__name__
            if self._cache is not None:
                cached, age = self._cache.get(name, query, 3)
                if cached is not None:
                    self.cache_report[name] = {"hit": True, "age_sec": age}
                    self.console.print(
                        f"  [green]⚡ 캐시 적중: {name} (age {age}s)[/green]"
                    )
                    results.extend(PaperMetadata(**d) for d in cached)
                    continue
            self.cache_report[name] = {"hit": False, "age_sec": None}
            live.append((client, name))

        if live:
            nested = await asyncio.gather(
                *[c.search(query) for c, _ in live], return_exceptions=True
            )
            for (_, name), res in zip(live, nested):
                if isinstance(res, Exception):
                    self.console.print(f"  [red]⚠️ API 호출 중 예외 발생: {res}[/red]")
                    continue
                results.extend(res)
                if self._cache is not None:
                    self._cache.put(name, query, 3, [p.model_dump(mode="json") for p in res])

        return self._smart_noise_filter(results)
    
    def _smart_noise_filter(self, papers: List[PaperMetadata]) -> List[PaperMetadata]:
        clean_papers = []
        noise_keywords = ["frontmatter", "editorial", "table of contents"]
        
        for p in papers:
            if any(keyword in p.title.lower() for keyword in noise_keywords):
                p.is_noise = True
                self.console.print(f"  [red]x Filtered noise:[/red] {p.title}")
            else:
                clean_papers.append(p)
                
        return clean_papers

    def generate_digest(self, papers: List[PaperMetadata]):
        self.console.print("\n[bold yellow]📑 Recon Digest Report[/bold yellow]")
        from omni_academic.audit.forensic import is_valid_doi_syntax

        for idx, p in enumerate(papers, 1):
            if p.doi and not is_valid_doi_syntax(p.doi):
                self.console.print(
                    f"  [red]⚠️ DOI 문법 위반(유령 인용 의심): {p.doi}[/red]"
                )
            source = f"DOI: {p.doi}" if p.doi else f"URL: {p.url}"
            content = f"**Authors**: {', '.join(p.authors)}\n**Citations**: {p.citation_count}\n**Source**: {source}\n\n**Abstract**: {p.abstract}"
            self.console.print(Panel(content, title=f"[{idx}] {p.title}", border_style="green"))
        
        self.console.print("\n[bold blue]수퍼바이저 대기 중...[/bold blue] 딥다이브할 논문 번호를 승인(Approve)해 주십시오.")
