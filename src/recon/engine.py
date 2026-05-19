import os
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
                papers = self._parse(response.content)
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]KCI API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]KCI 네트워크 요청 실패: {e}[/bold red]")

        return papers

    @classmethod
    def _parse(cls, content: bytes) -> List[PaperMetadata]:
        papers = []
        try:
            root = ET.fromstring(content)
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


_NCBI_COMMON = {"db": "pubmed", "tool": "omni-academic-framework",
                "email": "noreply@example.com"}


class PubMedClient(BaseAPIClient):
    """PubMed/NCBI E-utilities 플러그인 (키 불필요, httpx-native, 2-step).

    esearch(JSON)로 PMID 목록 → esummary(JSON)로 메타데이터. 검증된 한계:
    esummary에는 abstract가 없다(본문은 Phase B). 추측 파싱을 피하려고
    실제 응답 스키마(esearchresult.idlist / result[<uid>])에만 의존한다.
    """

    ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

    @staticmethod
    def _parse(payload: dict) -> List[PaperMetadata]:
        result = payload.get("result", {}) or {}
        papers: List[PaperMetadata] = []
        for uid in result.get("uids", []) or []:
            rec = result.get(uid, {}) or {}
            title = _norm(rec.get("title"))
            if not title:
                continue
            doi = next(
                (a.get("value") for a in rec.get("articleids", [])
                 if a.get("idtype") == "doi"),
                None,
            )
            papers.append(PaperMetadata(
                title=f"[PubMed] {title}",
                authors=[_norm(a.get("name")) for a in rec.get("authors", [])
                         if a.get("name")] or ["저자 미상"],
                abstract="초록 없음 (PubMed esummary 미제공 — 본문은 Phase B)",
                doi=doi,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
                venue=_norm(rec.get("source")) or None,
            ))
        return papers

    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                es = await client.get(self.ESEARCH, params={
                    **_NCBI_COMMON, "term": query,
                    "retmax": max_results, "retmode": "json",
                })
                es.raise_for_status()
                ids = es.json().get("esearchresult", {}).get("idlist", []) or []
                if not ids:
                    return []
                summ = await client.get(self.ESUMMARY, params={
                    **_NCBI_COMMON, "id": ",".join(ids), "retmode": "json",
                })
                summ.raise_for_status()
                return self._parse(summ.json())
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]PubMed API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]PubMed 네트워크 요청 실패: {e}[/bold red]")
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]PubMed 응답 파싱 실패: {e}[/bold red]")
        return []


class OpenAlexClient(BaseAPIClient):
    """OpenAlex 플러그인 (CC0, 키 불필요, httpx-native, 단일 호출).

    Crossref 상위호환 — 인문/신학 등 DOI 빈약 영역 커버. abstract는
    inverted-index 형태라 위치 정렬로 재구성한다(없을 수 있음).
    """

    @staticmethod
    def _abstract(inv: Optional[dict]) -> str:
        if not inv:
            return "초록 없음"
        pairs = [(pos, w) for w, ps in inv.items() for pos in ps]
        text = _norm(" ".join(w for _, w in sorted(pairs)))
        return text[:200] + "..." if len(text) > 200 else (text or "초록 없음")

    @staticmethod
    def _parse(payload: dict) -> List[PaperMetadata]:
        papers: List[PaperMetadata] = []
        for r in payload.get("results", []) or []:
            title = _norm(r.get("title") or r.get("display_name"))
            if not title:
                continue
            loc = r.get("primary_location") or {}
            src = loc.get("source") or {}
            doi = r.get("doi")
            papers.append(PaperMetadata(
                title=f"[OpenAlex] {title}",
                authors=[_norm((a.get("author") or {}).get("display_name"))
                         for a in r.get("authorships", [])
                         if (a.get("author") or {}).get("display_name")] or ["저자 미상"],
                abstract=OpenAlexClient._abstract(r.get("abstract_inverted_index")),
                doi=doi.replace("https://doi.org/", "") if doi else None,
                url=loc.get("landing_page_url") or doi or r.get("id"),
                citation_count=r.get("cited_by_count", 0) or 0,
                venue=_norm(src.get("display_name")) or None,
            ))
        return papers

    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        params = urllib.parse.urlencode({
            "search": query, "per-page": max_results,
            "mailto": "noreply@example.com",
        })
        url = f"https://api.openalex.org/works?{params}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return self._parse(response.json())
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]OpenAlex API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]OpenAlex 네트워크 요청 실패: {e}[/bold red]")
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]OpenAlex 응답 파싱 실패: {e}[/bold red]")
        return []


class CitationGraphClient:
    """Snowballing — 인용 네트워크 정찰 (OpenAlex 백엔드).

    의도적으로 `BaseAPIClient`를 상속하지 않는다: `snowball`을 인터페이스에
    얹으면 KCI/EconBiz/arxiv가 전부 NotImplementedError 스텁을 갖게 되어
    피어리뷰가 지적한 인터페이스-오염 안티패턴이 재발한다. Snowball은
    별개의 On-Demand 모드이며 OpenAlex(가장 깨끗한 오픈 인용그래프) 단일
    백엔드로만 동작한다.
    """

    BASE = "https://api.openalex.org/works"

    @staticmethod
    def _seed_id(work: dict) -> Optional[str]:
        oid = (work or {}).get("id") or ""
        return oid.rsplit("/", 1)[-1] or None  # https://openalex.org/Wxxxx -> Wxxxx

    async def snowball(self, doi: str, direction: str = "both",
                       max_results: int = 10) -> List[PaperMetadata]:
        doi = (doi or "").strip().replace("https://doi.org/", "")
        if not doi:
            console.print("[bold red]snowball: DOI가 비어 있습니다.[/bold red]")
            return []
        papers: List[PaperMetadata] = []
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                seed_resp = await client.get(
                    f"{self.BASE}/doi:{doi}", params={"mailto": "noreply@example.com"}
                )
                seed_resp.raise_for_status()
                wid = self._seed_id(seed_resp.json())
                if not wid:
                    console.print("[bold red]snowball: seed 논문 식별 실패.[/bold red]")
                    return []

                wanted = []
                if direction in ("both", "references"):
                    wanted.append(("references", f"cited_by:{wid}"))
                if direction in ("both", "citations"):
                    wanted.append(("citations", f"cites:{wid}"))

                for _, filt in wanted:
                    r = await client.get(self.BASE, params={
                        "filter": filt, "per-page": max_results,
                        "mailto": "noreply@example.com",
                    })
                    r.raise_for_status()
                    papers.extend(OpenAlexClient._parse(r.json()))
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]Snowball API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]Snowball 네트워크 요청 실패: {e}[/bold red]")
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]Snowball 응답 파싱 실패: {e}[/bold red]")

        # url/doi 기준 중복 제거
        seen, uniq = set(), []
        for p in papers:
            k = p.doi or p.url or p.title
            if k in seen:
                continue
            seen.add(k)
            uniq.append(p)
        return uniq


class SerpApiScholarClient(BaseAPIClient):
    """SerpAPI Google Scholar API 어댑터 (비동기).
    이 플러그인은 Google Scholar의 차단을 우회하여 키워드 검색을 안정적으로 수행합니다.
    SERPAPI_API_KEY 환경변수가 필요합니다. 없을 경우 로컬 라이트판다 스크래핑으로 폴백합니다.
    """
    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        api_key = os.environ.get("SERPAPI_API_KEY")
        if not api_key:
            console.print("[yellow]SerpAPI: SERPAPI_API_KEY 환경변수가 설정되지 않았습니다. Local Browser Scraping (Lightpanda) 폴백을 시도합니다...[/yellow]")
            return await self._search_via_local_scraper(query, max_results)

        params = {
            "engine": "google_scholar",
            "q": query,
            "num": max_results,
            "api_key": api_key,
        }
        url = "https://serpapi.com/search"
        papers = []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                results = data.get("organic_results", [])
                for rec in results:
                    title = _norm(rec.get("title"))
                    if not title:
                        continue
                    
                    # 저자 파싱
                    summary = rec.get("publication_info", {}).get("summary", "")
                    authors = []
                    venue = None
                    if summary:
                        parts = summary.split(" - ")
                        if parts:
                            authors = [a.strip() for a in parts[0].split(",")]
                            if len(parts) > 1:
                                venue = _norm(parts[1])
                    
                    # 인용수 파싱
                    citation_count = 0
                    cited_by = rec.get("inline_links", {}).get("cited_by", {})
                    if isinstance(cited_by, dict):
                        citation_count = cited_by.get("total", 0)

                    papers.append(PaperMetadata(
                        title=f"[Google Scholar] {title}",
                        authors=authors or ["저자 미상"],
                        abstract=_norm(rec.get("snippet"))[:200] or "초록 없음",
                        url=rec.get("link"),
                        citation_count=citation_count,
                        venue=venue,
                    ))
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]SerpAPI API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]SerpAPI 네트워크 요청 실패: {e}[/bold red]")
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]SerpAPI 응답 파싱 실패: {e}[/bold red]")

        return papers

    async def _search_via_local_scraper(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        import urllib.parse
        import subprocess

        lightpanda_path = "/Users/msn/Desktop/MS_Dev.nosync/bin/lightpanda"
        if not os.path.exists(lightpanda_path):
            console.print("[bold red]SerpAPI: Local Browser (Lightpanda) 바이너리가 존재하지 않아 스크래핑을 취소합니다.[/bold red]")
            return []

        encoded_query = urllib.parse.quote(query)
        url = f"https://scholar.google.com/scholar?q={encoded_query}&hl=en"
        console.print(f"  [italic]Local browser scraper (Lightpanda) 가동... URL: {url}[/italic]")

        cmd = [lightpanda_path, "fetch", "--dump", "html", url]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                console.print(f"[bold red]라이트판다 실행 실패 (exit code {proc.returncode}): {stderr.decode(errors='ignore')}[/bold red]")
                return []

            html_content = stdout.decode("utf-8", errors="ignore")
            return self._parse_scholar_html(html_content, max_results)
        except Exception as e:
            console.print(f"[bold red]라이트판다 구동 중 오류 발생: {e}[/bold red]")
            return []

    def _parse_scholar_html(self, html: str, max_results: int) -> List[PaperMetadata]:
        import re
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        papers = []

        results = soup.select(".gs_r.gs_or.gs_scl, .gs_r")
        for res in results:
            if len(papers) >= max_results:
                break

            title_el = res.select_one(".gs_rt a")
            if not title_el:
                title_el = res.select_one(".gs_rt")
                if not title_el:
                    continue
                title = _norm(title_el.get_text())
                url = None
            else:
                title = _norm(title_el.get_text())
                url = title_el.get("href")

            # [CITATION], [HTML], [PDF] 등 구글 스콜라 접두사 제거
            if title.startswith("[") and "]" in title:
                title = title.split("]", 1)[-1].strip()

            if not title:
                continue

            meta_el = res.select_one(".gs_a")
            authors = ["저자 미상"]
            venue = None
            if meta_el:
                meta_text = meta_el.get_text()
                parts = [p.strip() for p in meta_text.split(" - ")]
                if parts:
                    authors = [a.strip() for a in parts[0].split(",")]
                    if len(parts) > 1:
                        venue = _norm(parts[1])

            snippet_el = res.select_one(".gs_rs")
            abstract = "초록 없음"
            if snippet_el:
                abstract = _norm(snippet_el.get_text())

            citation_count = 0
            fl_links = res.select(".gs_fl a")
            for link in fl_links:
                link_text = link.get_text()
                if "Cited by" in link_text or "인용" in link_text:
                    num_match = re.search(r"\d+", link_text)
                    if num_match:
                        citation_count = int(num_match.group())
                        break

            papers.append(PaperMetadata(
                title=f"[Google Scholar] {title}",
                authors=authors,
                abstract=abstract[:200] + "..." if len(abstract) > 200 else abstract,
                url=url,
                citation_count=citation_count,
                venue=venue,
            ))

        return papers


class SemanticScholarClient(BaseAPIClient):
    """Semantic Scholar 공식 Web API 어댑터 (비동기).
    SEMANTIC_SCHOLAR_API_KEY 환경변수가 설정되어 있으면 헤더에 주입하여
    더 높은 Rate Limit으로 고속 조회가 가능합니다. 없어도 3초/1회 속도 한도로 동작합니다.
    """
    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        headers = {}
        if api_key:
            headers["x-api-key"] = api_key

        params = {
            "query": query,
            "limit": max_results,
            "fields": "title,authors,abstract,externalIds,url,citationCount,venue",
        }
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        papers = []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                for item in data.get("data", []) or []:
                    title = _norm(item.get("title"))
                    if not title:
                        continue
                    
                    authors = [
                        _norm(a.get("name")) for a in item.get("authors", [])
                        if a.get("name")
                    ]
                    doi = (item.get("externalIds") or {}).get("DOI")
                    
                    papers.append(PaperMetadata(
                        title=f"[Semantic Scholar] {title}",
                        authors=authors or ["저자 미상"],
                        abstract=_norm(item.get("abstract"))[:200] or "초록 없음",
                        doi=doi,
                        url=item.get("url"),
                        citation_count=item.get("citationCount") or 0,
                        venue=_norm(item.get("venue")) or None,
                    ))
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]Semantic Scholar API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]Semantic Scholar 네트워크 요청 실패: {e}[/bold red]")
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]Semantic Scholar 응답 파싱 실패: {e}[/bold red]")

        return papers


# 클라이언트 이름 → 구현. 도메인↔클라이언트 매핑은 코드가 아니라
# lenses/*.yaml 의 recon_clients 가 결정한다(헌법 §2: 도메인 독립성).
CLIENT_FACTORY = {
    "arxiv": ArxivClient,
    "kci": KCIClient,
    "crossref": CrossrefClient,
    "econbiz": EconBizClient,
    "pubmed": PubMedClient,
    "openalex": OpenAlexClient,
    "serpapi_scholar": SerpApiScholarClient,
    "semanticscholar": SemanticScholarClient,
}


class ReconEngine:
    def __init__(self, lens_dir: str = "lenses", *, use_cache: bool = True,
                 cache_dir: str = ".cache"):
        self.console = console
        self.lens_dir = lens_dir
        self.use_cache = use_cache
        self._cache = None
        if use_cache:
            from src.store.recon_cache import ReconCache
            self._cache = ReconCache(base=cache_dir)
        # manifest 자기검증용 — client별 캐시 적중/나이 기록
        self.cache_report: dict = {}

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
