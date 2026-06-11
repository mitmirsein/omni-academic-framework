import urllib.parse
from typing import List

import httpx

from omni_academic.recon.clients.base import (
    BaseAPIClient,
    PaperMetadata,
    _norm,
    console,
)


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
