import urllib.parse
from typing import List

import httpx

from omni_academic.recon.clients.base import (
    BaseAPIClient,
    PaperMetadata,
    _norm,
    console,
)


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
