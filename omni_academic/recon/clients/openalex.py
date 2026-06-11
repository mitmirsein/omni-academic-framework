import urllib.parse
from typing import List, Optional

import httpx

from omni_academic.recon.clients.base import (
    BaseAPIClient,
    PaperMetadata,
    _norm,
    console,
)


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
