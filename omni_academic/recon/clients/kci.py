import os
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List

import httpx

from omni_academic.recon.clients.base import (
    BaseAPIClient,
    PaperMetadata,
    _norm,
    console,
)


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
