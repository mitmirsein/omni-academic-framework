import asyncio
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Optional

import httpx
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel

console = Console()


def _norm(text: Optional[str]) -> str:
    """실제 개행/탭/중복 공백을 단일 공백으로 정규화한다."""
    if not text:
        return ""
    return " ".join(text.split())


def _findtext(elem, path: str, ns: dict) -> Optional[str]:
    """요소 누락 시 None.text 크래시를 막는 안전 추출기."""
    found = elem.find(path, ns)
    return found.text if found is not None and found.text else None

class PaperMetadata(BaseModel):
    title: str
    authors: List[str]
    abstract: Optional[str] = "No abstract available"
    doi: Optional[str] = None
    url: Optional[str] = None
    citation_count: int = 0
    venue: Optional[str] = None
    is_noise: bool = False

class BaseAPIClient:
    """비동기 정찰 API 어댑터 인터페이스"""
    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        raise NotImplementedError

class ArxivClient(BaseAPIClient):
    """arXiv 어댑터. 손수 짠 Atom XML 파싱 대신 검증된 `arxiv` 라이브러리에
    페이지네이션·재시도·정렬을 위임한다. 라이브러리는 동기(+자체 rate-limit)
    이므로 `asyncio.to_thread`로 오프로드해 async 엔진을 블로킹하지 않는다.
    """

    @staticmethod
    def _fetch(query: str, max_results: int) -> List[PaperMetadata]:
        import arxiv

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        papers: List[PaperMetadata] = []
        for r in client.results(search):
            title = _norm(r.title)
            if not title:
                continue
            abstract = _norm(r.summary)
            papers.append(PaperMetadata(
                title=f"[arXiv] {title}",
                authors=[_norm(a.name) for a in r.authors] or ["저자 미상"],
                abstract=abstract[:200] + "..." if len(abstract) > 200 else (abstract or "초록 없음"),
                doi=r.doi,
                url=r.entry_id,
                venue=r.journal_ref or None,
            ))
        return papers

    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        try:
            return await asyncio.to_thread(self._fetch, query, max_results)
        except ModuleNotFoundError:
            console.print(
                "[bold red]arXiv: 'arxiv' 패키지가 필요합니다 (uv sync).[/bold red]"
            )
        except Exception as e:  # arxiv.ArxivError 등 라이브러리 예외 포함
            console.print(f"[bold red]arXiv 검색 실패: {e}[/bold red]")
        return []

class KCIClient(BaseAPIClient):
    """실시간 한국학술지인용색인(KCI) 오픈 API 플러그인 (비동기)"""
    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        # KCI Open API 연동 구조체. 엘리먼트 경로는 공개 스키마 기준 추정값이며
        # 미검증이다 → 실패 시 빈 결과로 삼키지 않고 명시적으로 신호한다.
        params = urllib.parse.urlencode({
            "apiCode": "articleSearch",
            "title": query,
            "displayCount": max_results,
        })
        url = f"https://open.kci.go.kr/po/openapi/openApiSearch.kci?{params}"
        papers = []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                root = ET.fromstring(response.content)

                for record in root.findall('.//record'):
                    title = _findtext(record, './/articleInfo/title-group/article-title', {})
                    abstract = _findtext(record, './/articleInfo/abstract-group/abstract', {})
                    url_link = _findtext(record, './/articleInfo/url', {})
                    authors = [
                        a.text for a in record.findall('.//author-group/author') if a.text
                    ]

                    papers.append(PaperMetadata(
                        title=f"[KCI] {_norm(title) or '제목 없음'}",
                        authors=authors or ["저자 미상"],
                        abstract=_norm(abstract)[:200] or "초록 없음",
                        url=url_link,
                    ))
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]KCI API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]KCI 네트워크 요청 실패: {e}[/bold red]")
        except ET.ParseError as e:
            console.print(f"[bold red]KCI XML 파싱 실패(스키마 불일치 가능): {e}[/bold red]")

        return papers

class CrossrefClient(BaseAPIClient):
    """Crossref REST API 플러그인 (api.crossref.org, 키 불필요, 비동기)."""
    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        params = urllib.parse.urlencode({"query": query, "rows": max_results})
        url = f"https://api.crossref.org/works?{params}"
        papers = []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url, headers={"User-Agent": "omni-academic-framework/0.1 (mailto:noreply@example.com)"}
                )
                response.raise_for_status()
                items = response.json().get("message", {}).get("items", [])

                for it in items:
                    title_list = it.get("title") or []
                    title = _norm(title_list[0]) if title_list else ""
                    if not title:
                        continue
                    authors = [
                        _norm(f"{a.get('given', '')} {a.get('family', '')}")
                        for a in it.get("author", [])
                    ]
                    doi = it.get("DOI")
                    papers.append(PaperMetadata(
                        title=f"[Crossref] {title}",
                        authors=[a for a in authors if a] or ["저자 미상"],
                        abstract=_norm(it.get("abstract"))[:200] or "초록 없음",
                        doi=doi,
                        url=it.get("URL") or (f"https://doi.org/{doi}" if doi else None),
                        citation_count=it.get("is-referenced-by-count", 0),
                        venue=(it.get("container-title") or [None])[0],
                    ))
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]Crossref API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]Crossref 네트워크 요청 실패: {e}[/bold red]")
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]Crossref 응답 파싱 실패: {e}[/bold red]")

        return papers

class EconBizClient(BaseAPIClient):
    """EconBiz(ZBW) 오픈 REST API 플러그인 (키 불필요, 비동기).

    검증된 한계: search 응답에는 abstract·DOI가 없다(제목·저자·URL·subject만).
    추측 파싱을 피하기 위해 실제 v1 응답 스키마(`hits.hits[]`)에만 의존한다.
    """

    @staticmethod
    def _parse(payload: dict) -> List[PaperMetadata]:
        papers: List[PaperMetadata] = []
        for rec in (payload.get("hits", {}) or {}).get("hits", []) or []:
            title = _norm(rec.get("title"))
            if not title:
                continue
            authors = rec.get("person") or rec.get("creator") or rec.get("contributor") or []
            urls = rec.get("identifier_url") or []
            url = urls[0] if urls else (
                f"https://www.econbiz.de/Record/{rec['id']}" if rec.get("id") else None
            )
            papers.append(PaperMetadata(
                title=f"[EconBiz] {title}",
                authors=[_norm(a) for a in authors if a] or ["저자 미상"],
                abstract="초록 없음 (EconBiz search 미제공 — 본문은 Phase B)",
                url=url,
                venue=_norm((rec.get("series") or [None])[0]) or None,
            ))
        return papers

    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        params = urllib.parse.urlencode({"q": query, "size": max_results})
        url = f"https://api.econbiz.de/v1/search?{params}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return self._parse(response.json())
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]EconBiz API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]EconBiz 네트워크 요청 실패: {e}[/bold red]")
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]EconBiz 응답 파싱 실패: {e}[/bold red]")
        return []


# 클라이언트 이름 → 구현. 도메인↔클라이언트 매핑은 코드가 아니라
# lenses/*.yaml 의 recon_clients 가 결정한다(헌법 §2: 도메인 독립성).
CLIENT_FACTORY = {
    "arxiv": ArxivClient,
    "kci": KCIClient,
    "crossref": CrossrefClient,
    "econbiz": EconBizClient,
}


class ReconEngine:
    def __init__(self, lens_dir: str = "lenses"):
        self.console = console
        self.lens_dir = lens_dir

    def _resolve_clients(self, lens: str) -> List[BaseAPIClient]:
        from src.config.lens import (
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

        self.console.print("  - [italic]API 플러그인 병렬 스크래핑(Gathering) 시작...[/italic]")
        
        # asyncio를 통한 멀티 API 동시 호출 (성능 최적화)
        tasks = [client.search(query) for client in clients]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)
        
        results: List[PaperMetadata] = []
        for res in results_nested:
            if isinstance(res, Exception):
                self.console.print(f"  [red]⚠️ API 호출 중 예외 발생: {res}[/red]")
            else:
                results.extend(res)
            
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
        from src.audit.forensic import is_valid_doi_syntax

        for idx, p in enumerate(papers, 1):
            if p.doi and not is_valid_doi_syntax(p.doi):
                self.console.print(
                    f"  [red]⚠️ DOI 문법 위반(유령 인용 의심): {p.doi}[/red]"
                )
            source = f"DOI: {p.doi}" if p.doi else f"URL: {p.url}"
            content = f"**Authors**: {', '.join(p.authors)}\n**Citations**: {p.citation_count}\n**Source**: {source}\n\n**Abstract**: {p.abstract}"
            self.console.print(Panel(content, title=f"[{idx}] {p.title}", border_style="green"))
        
        self.console.print("\n[bold blue]수퍼바이저 대기 중...[/bold blue] 딥다이브할 논문 번호를 승인(Approve)해 주십시오.")
