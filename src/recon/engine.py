import asyncio
import os
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
    """한국학술지인용색인(KCI) Open API 어댑터 (비동기).

    실 API 검증(2026-05): 루트는 `<MetaData>`이고 `key` 파라미터가
    필수다(없으면 `outputData/result/resultMsg`에 에러 메시지). 키 없는
    무료 호출 경로는 존재하지 않으므로, 키 미설정 시 빈 결과로 삼키지
    않고 정직하게 신호한다. **레코드(성공) 스키마는 키드 샘플 미확보로
    여전히 미검증** — 필드는 추측 경로가 아니라 local-name 휴리스틱으로
    추출한다(허위 정밀 주장 금지).
    """

    # 실 검증(2026-05): 결과행 a.subject(제목+상세링크) + ul.subject-info > li
    # (저자: poCretDetail / 학술지: ciSereInfoView). 검색은 POST 계약 필수.
    SEARCH_URL = "https://www.kci.go.kr/kciportal/po/search/poArtiSearList.kci"

    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        api_key = os.environ.get("KCI_API_KEY", "").strip()
        if not api_key:
            # Open API 키는 일반 사용자 비공개 → 검증된 POST 웹검색으로 우회.
            # (서버 렌더라 Lightpanda 불필요. GET은 검색어 무시 버그 — 폐기.)
            return await self._search_via_web(query, max_results)

        params = urllib.parse.urlencode({
            "apiCode": "articleSearch",
            "key": api_key,
            "title": query,
            "displayCount": max_results,
            "page": 1,
        })
        url = f"https://open.kci.go.kr/po/openapi/openApiSearch.kci?{params}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return self._parse(response.content)
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]KCI API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]KCI 네트워크 요청 실패: {e}[/bold red]")
        return []

    @staticmethod
    def _strip_ns(root):
        for el in root.iter():
            if isinstance(el.tag, str) and "}" in el.tag:
                el.tag = el.tag.rsplit("}", 1)[1]
        return root

    @staticmethod
    def _local(tag) -> str:
        return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""

    @classmethod
    def _parse(cls, content: bytes) -> List[PaperMetadata]:
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            console.print(f"[bold red]KCI XML 파싱 실패: {e}[/bold red]")
            return []
        cls._strip_ns(root)

        # 실 구조: MetaData/outputData/result/resultMsg = 에러/상태 봉투.
        records = [el for el in root.iter() if cls._local(el.tag) == "record"]
        if not records:
            msg_el = next(
                (el for el in root.iter() if cls._local(el.tag) == "resultmsg"), None
            )
            if msg_el is not None and (msg_el.text or "").strip():
                console.print(
                    f"[bold red]KCI 응답 실패(레코드 없음): {msg_el.text.strip()}[/bold red]"
                )
            return []

        # 레코드 필드 스키마 미검증 → 정밀 경로 추측 대신 local-name 휴리스틱.
        papers: List[PaperMetadata] = []
        for rec in records:
            title, url_link, abstract, authors = None, None, None, []
            for el in rec.iter():
                name = cls._local(el.tag)
                txt = (el.text or "").strip()
                if not txt:
                    continue
                if "title" in name and "group" not in name and not title:
                    title = txt
                elif name == "author":
                    authors.append(txt)
                elif "url" in name and not url_link:
                    url_link = txt
                elif "abstract" in name and "group" not in name and not abstract:
                    abstract = txt
            papers.append(PaperMetadata(
                title=f"[KCI] {_norm(title) or '제목 없음'}",
                authors=authors or ["저자 미상"],
                abstract=_norm(abstract)[:200] or "초록 없음",
                url=url_link,
            ))
        return papers

    @staticmethod
    def _html_has_query(html: str, query: str) -> bool:
        """검색어가 응답 본문에 실제로 반영됐는지(공백 정규화) 확인.

        KCI는 GET 쿼리를 무시하고 검색어 없는 인기 논문 목록을 렌더하는
        버그 클래스가 있다 → 검색어 미반영 응답은 0건으로 처리(오염 차단).
        """
        def canon(s: str) -> str:
            return "".join((s or "").split()).lower()

        hq = canon(html)
        tokens = [t for t in (query or "").split() if t.strip()]
        return any(canon(t) in hq for t in tokens) if tokens else False

    async def _search_via_web(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        """KCI 웹검색: 검증된 POST 계약으로 질의.

        실 검증(2026-05): `poArtiSearList.kci`는 GET `?searchQuery=`를
        무시하고 인기 논문(예: 췌장암/담도암)을 렌더한다 → 반드시
        `poSearchBean.conditionList=KEYALL` + `poSearchBean.keywordList`
        를 POST해야 검색어가 인정되며, 결과는 서버 렌더라 JS/Lightpanda
        없이 httpx만으로 파싱된다.
        """
        if not (query or "").strip():
            return []
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.post(
                    self.SEARCH_URL,
                    data={
                        "poSearchBean.conditionList": "KEYALL",
                        "poSearchBean.keywordList": query,
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Referer": "https://www.kci.go.kr/kciportal/main.kci",
                        "User-Agent": "Mozilla/5.0",
                    },
                )
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]KCI 웹검색 에러 (상태 {e.response.status_code})[/bold red]")
            return []
        except httpx.RequestError as e:
            console.print(f"[bold red]KCI 웹검색 네트워크 실패: {e}[/bold red]")
            return []

        # 안전장치: 검색어가 응답에 반영되지 않았으면(=GET 무시 버그 클래스)
        # 오염된 인기 목록 대신 정직하게 0건 반환.
        if not self._html_has_query(html, query):
            console.print(
                "[bold yellow]KCI: 응답에 검색어 미반영 — 오염 방지로 0건 처리[/bold yellow]"
            )
            return []
        papers = self._parse_html(html, max_results)
        return await self._enrich_via_oai(papers)

    @staticmethod
    async def _enrich_via_oai(papers: List[PaperMetadata]) -> List[PaperMetadata]:
        """1단계(웹 검색 후보) → 2단계(OAI-PMH 정밀 메타데이터) 브리지.

        웹 목록뷰는 초록이 없다. 후보 URL의 artiId를 뽑아 OAI-PMH
        `GetRecord`로 정밀 메타데이터(초록·DOI)를 best-effort 보강한다.
        GetRecord가 차단/실패하면 웹 필드를 그대로 유지(graceful, 무날조).
        `OMNI_KCI_OAI_ENRICH=0`으로 비활성화 가능.
        """
        import os
        import re

        if os.environ.get("OMNI_KCI_OAI_ENRICH", "1").strip() == "0":
            return papers
        oai = KciOaiClient()
        for p in papers:
            m = re.search(r"artiId=([A-Za-z0-9]+)", p.url or "")
            if not m:
                continue
            rec = await oai.get_record(m.group(1))
            if rec is None:
                continue  # 차단/실패 → 웹 필드 유지
            # 웹의 title/authors/venue는 유지, OAI의 초록·DOI만 보강
            if rec.abstract and not rec.abstract.startswith("초록 없음"):
                p.abstract = rec.abstract
            if rec.doi and not p.doi:
                p.doi = rec.doi
        return papers

    @classmethod
    def _parse_html(cls, html: str, max_results: int = 3) -> List[PaperMetadata]:
        """KCI 웹검색 렌더 DOM 파서. 셀렉터는 실 lightpanda 렌더 결과를
        직접 캡처해 검증(2026-05)했고 test_kci.py가 실 fragment로 스냅샷
        고정한다. 목록뷰엔 초록이 없다 → 정직하게 미제공 표기."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        papers: List[PaperMetadata] = []
        for a in soup.select("a.subject"):
            title = _norm(a.get_text())
            if not title:
                continue
            href = a.get("href") or ""
            url_link = ("https://www.kci.go.kr" + href) if href.startswith("/") else (href or None)

            authors, venue = [], None
            td = a.find_parent("td")
            info = td.select_one("ul.subject-info") if td else None
            if info:
                for li in info.select("li"):
                    link = li.find("a")
                    if not link:
                        continue
                    h = link.get("href") or ""
                    text = _norm(link.get_text())
                    if "poCretDetail" in h and text:
                        authors.append(text)
                    elif venue is None and ("ciSereInfoView" in h or "poInsiSearSoceView" in h) and text:
                        venue = text

            papers.append(PaperMetadata(
                title=f"[KCI] {title}",
                authors=authors or ["저자 미상"],
                abstract="초록 없음 (KCI 목록 미제공 — 본문은 Phase B)",
                url=url_link,
                venue=venue,
            ))
            if len(papers) >= max_results:
                break
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


class DBLPClient(BaseAPIClient):
    """DBLP 검색 API 플러그인 (dblp.org, 키 불필요, httpx-native, 단일 호출).

    CS/공학 서지 커버리지 강화. 실 검증(2026-05): `result.hits.hit[].info`에
    제목·저자·venue·year·doi·ee(landing)가 담긴다. 검증된 한계: DBLP는
    abstract와 citation_count를 제공하지 않는다(서지 메타데이터만) →
    PubMed/EconBiz와 동일하게 정직히 미제공 표기. 추측 파싱을 피해 실제
    응답 스키마에만 의존하되, DBLP JSON이 **항목 1개일 때 list 대신 단일
    객체**를 직렬화하는 알려진 변덕(hit·author 모두)을 정규화한다.
    """

    SEARCH_URL = "https://dblp.org/search/publ/api"

    @staticmethod
    def _as_list(value) -> list:
        """DBLP는 항목이 1개면 list가 아니라 단일 객체를 반환한다 → 항상 list."""
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    @classmethod
    def _authors(cls, info: dict) -> List[str]:
        block = info.get("authors") or {}
        names = []
        for a in cls._as_list(block.get("author")):
            name = _norm(a.get("text")) if isinstance(a, dict) else _norm(str(a))
            if name:
                names.append(name)
        return names

    @classmethod
    def _parse(cls, payload: dict) -> List[PaperMetadata]:
        hits = ((payload.get("result") or {}).get("hits") or {})
        papers: List[PaperMetadata] = []
        for hit in cls._as_list(hits.get("hit")):
            info = (hit or {}).get("info") or {}
            title = _norm(info.get("title"))
            if not title:
                continue
            doi = info.get("doi")
            # venue는 드물게 list로도 온다(복수 게재) → 정규화.
            venue = info.get("venue")
            if isinstance(venue, list):
                venue = ", ".join(_norm(v) for v in venue if v) or None
            else:
                venue = _norm(venue) or None
            papers.append(PaperMetadata(
                title=f"[DBLP] {title}",
                authors=cls._authors(info) or ["저자 미상"],
                abstract="초록 없음 (DBLP search 미제공 — 본문은 Phase B)",
                doi=doi,
                url=info.get("ee") or info.get("url")
                or (f"https://doi.org/{doi}" if doi else None),
                venue=venue,
            ))
        return papers

    async def search(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        params = urllib.parse.urlencode({"q": query, "format": "json", "h": max_results})
        url = f"{self.SEARCH_URL}?{params}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": "omni-academic-framework/0.1 (mailto:noreply@example.com)"},
                )
                response.raise_for_status()
                return self._parse(response.json())
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]DBLP API 에러 (상태 코드 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]DBLP 네트워크 요청 실패: {e}[/bold red]")
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]DBLP 응답 파싱 실패: {e}[/bold red]")
        return []


class KciOaiClient:
    """KCI OAI-PMH 수확 클라이언트 (무키·표준 oai_dc).

    실 검증(2026-05): base `https://open.kci.go.kr/oai/request`, 무인증,
    포맷 oai_dc/oai_kci, set ARTI/ARTI_CONF/JOUR, 식별자
    `oai:kci.go.kr:ARTI/{artiId}`. OAI-PMH는 *검색*이 아니라 *수확*
    프로토콜(키워드 질의 없음)이라 `BaseAPIClient`(search)를 상속하지
    않는다(인터페이스 비오염 — Snowball과 동일 원칙). 파싱은 OAI-PMH 2.0
    + Dublin Core **표준**에만 의존하고 네임스페이스는 local-name으로
    무력화한다(KCI 고유 경로 추측 0).
    """

    BASE = "https://open.kci.go.kr/oai/request"
    SETS = {"ARTI", "ARTI_CONF", "JOUR"}
    MAX_PAGES = 50  # resumptionToken 추종 안전 상한 (runaway 방지)

    @staticmethod
    def _local(tag) -> str:
        return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""

    @classmethod
    def _parse(cls, content: bytes) -> List[PaperMetadata]:
        # 하위호환: 레코드만 반환(기존 테스트 계약 유지).
        return cls._parse_page(content)[0]

    @classmethod
    def _parse_page(cls, content: bytes):
        """(records, resumption_token) 반환. OAI-PMH 페이지네이션용.

        빈/부재 resumptionToken은 OAI 규격상 '마지막 페이지' → None.
        """
        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            console.print(f"[bold red]KCI OAI XML 파싱 실패: {e}[/bold red]")
            return [], None
        L = cls._local
        err = next((el for el in root.iter() if L(el.tag) == "error"), None)
        if err is not None:
            console.print(
                f"[bold red]KCI OAI 오류: {err.get('code') or ''} "
                f"{(err.text or '').strip()}[/bold red]"
            )
            return [], None
        tok_el = next(
            (el for el in root.iter() if L(el.tag) == "resumptiontoken"), None
        )
        token = (tok_el.text or "").strip() if tok_el is not None else ""
        token = token or None
        papers: List[PaperMetadata] = []
        for rec in [el for el in root.iter() if L(el.tag) == "record"]:
            header = next((c for c in rec if L(c.tag) == "header"), None)
            if header is not None and header.get("status") == "deleted":
                continue
            ident = ""
            if header is not None:
                ide = next((c for c in header if L(c.tag) == "identifier"), None)
                ident = (ide.text or "").strip() if ide is not None else ""
            arti_id = ident.rsplit("/", 1)[-1] if "/" in ident else ""
            md = next((c for c in rec if L(c.tag) == "metadata"), None)
            title, abstract, doi = None, None, None
            authors: List[str] = []
            if md is not None:
                for el in md.iter():
                    name, txt = L(el.tag), _norm(el.text)
                    if not txt:
                        continue
                    if name == "title" and not title:
                        title = txt
                    elif name == "creator":
                        authors.append(txt)
                    elif name == "description" and not abstract:
                        abstract = txt
                    elif name == "identifier" and doi is None and txt.lower().startswith("10."):
                        doi = txt
            # url: 검증된 식별자 체계(oai:kci.go.kr:ARTI/{artiId}) +
            # 렌더 DOM에서 확인한 ciSereArtiView 패턴 → 둘 다 실측 검증.
            url = (
                "https://www.kci.go.kr/kciportal/ci/sereArticleSearch/"
                f"ciSereArtiView.kci?sereArticleSearchBean.artiId={arti_id}"
                if arti_id else None
            )
            papers.append(PaperMetadata(
                title=f"[KCI] {title or '제목 없음'}",
                authors=authors or ["저자 미상"],
                abstract=(abstract[:200] if abstract else "초록 없음"),
                doi=doi,
                url=url,
            ))
        return papers, token

    async def harvest(self, set_spec: str = "ARTI", max_records: int = 20,
                      metadata_prefix: str = "oai_dc") -> List[PaperMetadata]:
        set_spec = (set_spec or "ARTI").strip().upper()
        if set_spec not in self.SETS:
            console.print(
                f"[bold red]KCI OAI: 알 수 없는 set '{set_spec}' "
                f"(허용: {sorted(self.SETS)})[/bold red]"
            )
            return []

        # OAI-PMH 규격: 1페이지는 verb+metadataPrefix+set, 이후 페이지는
        # verb+resumptionToken만(다른 인자 동반 금지).
        params = {
            "verb": "ListRecords",
            "metadataPrefix": metadata_prefix,
            "set": set_spec,
        }
        papers: List[PaperMetadata] = []
        seen_tokens: set = set()
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                for _page in range(self.MAX_PAGES):
                    url = f"{self.BASE}?{urllib.parse.urlencode(params)}"
                    resp = await client.get(
                        url, headers={"User-Agent": "omni-academic-framework/0.6"}
                    )
                    resp.raise_for_status()
                    page_papers, token = self._parse_page(resp.content)
                    papers.extend(page_papers)
                    if len(papers) >= max_records or not token:
                        break
                    if token in seen_tokens:  # 토큰 반복 → 루프 방지
                        break
                    seen_tokens.add(token)
                    params = {"verb": "ListRecords", "resumptionToken": token}
                else:
                    console.print(
                        f"[yellow]KCI OAI: 페이지 상한({self.MAX_PAGES}) 도달 — "
                        "부분 결과 반환[/yellow]"
                    )
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]KCI OAI API 에러 (상태 {e.response.status_code})[/bold red]")
        except httpx.RequestError as e:
            console.print(f"[bold red]KCI OAI 네트워크 실패: {e}[/bold red]")
        # 네트워크 실패해도 그때까지 수확분은 정직하게 반환(부분 성공).
        return papers[:max_records]

    async def get_record(self, arti_id: str,
                         metadata_prefix: str = "oai_dc"):
        """OAI-PMH 표준 `GetRecord`로 단일 논문 정밀 메타데이터 조회.

        `GetRecord`는 OAI-PMH 2.0 필수 verb이고 응답은 ListRecords와 동일한
        oai_dc 레코드 구조라 검증된 `_parse`를 재사용한다. 단, KCI가 일부
        IP/환경에서 차단할 수 있으므로(개발 환경 실측: 400 차단 페이지)
        실패·비OAI 응답이면 None을 반환해 호출부가 graceful fallback
        하도록 한다(추측·날조 금지).
        """
        arti_id = (arti_id or "").strip()
        if not arti_id:
            return None
        params = urllib.parse.urlencode({
            "verb": "GetRecord",
            "metadataPrefix": metadata_prefix,
            "identifier": f"oai:kci.go.kr:ARTI/{arti_id}",
        })
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    f"{self.BASE}?{params}",
                    headers={"User-Agent": "omni-academic-framework/0.6"},
                )
                resp.raise_for_status()
                recs, _ = self._parse_page(resp.content)
                return recs[0] if recs else None
        except (httpx.HTTPStatusError, httpx.RequestError):
            return None


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
    SERPAPI_API_KEY가 없거나 API 요청이 명확히 실패하면 로컬 Lightpanda
    스크래핑으로 폴백합니다.
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
                if data.get("error"):
                    console.print(
                        f"[bold red]SerpAPI 응답 오류: {data.get('error')}[/bold red]"
                    )
                    return await self._search_via_local_scraper(query, max_results)
                
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
            return await self._search_via_local_scraper(query, max_results)
        except httpx.RequestError as e:
            console.print(f"[bold red]SerpAPI 네트워크 요청 실패: {e}[/bold red]")
            return await self._search_via_local_scraper(query, max_results)
        except (ValueError, KeyError) as e:
            console.print(f"[bold red]SerpAPI 응답 파싱 실패: {e}[/bold red]")
            return await self._search_via_local_scraper(query, max_results)

        return papers

    async def _search_via_local_scraper(self, query: str, max_results: int = 3) -> List[PaperMetadata]:
        import urllib.parse

        from src.config.tools import resolve_tool

        lightpanda_path = resolve_tool("OMNI_LIGHTPANDA_BIN", "lightpanda")
        if not os.path.exists(lightpanda_path):
            console.print(
                "[bold red]SerpAPI: Local Browser (Lightpanda) 바이너리가 "
                "OMNI_LIGHTPANDA_BIN 또는 PATH에 없어 스크래핑을 취소합니다.[/bold red]"
            )
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
    "dblp": DBLPClient,
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
