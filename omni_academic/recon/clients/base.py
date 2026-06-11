"""Recon 클라이언트 공통 계약과 헬퍼 (plug-and-play 어댑터 기반, 헌법 §5)."""

from typing import List, Optional

from pydantic import BaseModel
from rich.console import Console

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
