"""Recon API 클라이언트 패키지 — 엔진과 분리된 plug-and-play 어댑터(헌법 §5).

새 클라이언트는 파일 하나 추가 + CLIENT_FACTORY 등록으로 장착된다.
"""

from omni_academic.recon.clients.arxiv import ArxivClient
from omni_academic.recon.clients.base import BaseAPIClient, PaperMetadata
from omni_academic.recon.clients.crossref import CrossrefClient
from omni_academic.recon.clients.dblp import DBLPClient
from omni_academic.recon.clients.econbiz import EconBizClient
from omni_academic.recon.clients.kci import KCIClient, KciOaiClient
from omni_academic.recon.clients.openalex import CitationGraphClient, OpenAlexClient
from omni_academic.recon.clients.pubmed import PubMedClient
from omni_academic.recon.clients.scholar import SerpApiScholarClient
from omni_academic.recon.clients.semantic_scholar import SemanticScholarClient

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
    "SemanticScholarClient",
    "SerpApiScholarClient",
]
