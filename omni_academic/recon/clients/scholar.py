import asyncio
import os
import urllib.parse
from typing import List

import httpx

from omni_academic.recon.clients.base import (
    BaseAPIClient,
    PaperMetadata,
    _norm,
    console,
)


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

        from omni_academic.config.tools import resolve_tool

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
