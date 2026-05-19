import asyncio

import pytest

from src.recon import engine as engine_mod
from src.recon import scraper as scraper_mod
from src.recon.engine import (
    BaseAPIClient,
    CitationGraphClient,
    CLIENT_FACTORY,
    PaperMetadata,
    ReconEngine,
)
from src.recon.scraper import (
    JinaReaderScraper,
    PdfExtractorScraper,
    ScraperFactory,
)
from src.store.recon_cache import ReconCache


# ---- helpers: 오프라인 fake httpx ----------------------------------------
class _Resp:
    def __init__(self, json_data=None, headers=None, content=b""):
        self._json = json_data or {}
        self.headers = headers or {}
        self.content = content

    def json(self):
        return self._json

    def raise_for_status(self):
        pass


class _FakeClient:
    def __init__(self, *a, route=None, head_headers=None, **k):
        self._route = route or (lambda url, params: _Resp())
        self._head_headers = head_headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        return self._route(url, params or {})

    async def head(self, url):
        return _Resp(headers=self._head_headers)


# ---- 1. PDF scraper ------------------------------------------------------
def test_pdf_factory_routes_by_extension():
    assert isinstance(ScraperFactory.get_scraper("https://x.org/a.pdf"),
                      PdfExtractorScraper)
    assert isinstance(ScraperFactory.get_scraper("https://x.org/a.html"),
                      JinaReaderScraper)


def test_pypdf_extractor_honest_empty_on_garbage():
    assert PdfExtractorScraper._pypdf_to_text(b"not a real pdf") == ""


def test_detect_uses_content_type(monkeypatch):
    monkeypatch.setattr(
        scraper_mod.httpx, "AsyncClient",
        lambda *a, **k: _FakeClient(head_headers={"content-type": "application/pdf"}),
    )
    s = asyncio.run(ScraperFactory.detect("https://arxiv.org/pdf/2401.00001"))
    assert isinstance(s, PdfExtractorScraper)


# ---- 2. ReconCache -------------------------------------------------------
def test_recon_cache_roundtrip_and_ttl(tmp_path):
    c = ReconCache(base=str(tmp_path), ttl=86400)
    assert c.get("CrossrefClient", "q", 3) == (None, None)
    c.put("CrossrefClient", "q", 3, [{"title": "T", "authors": ["A"]}])
    payload, age = c.get("CrossrefClient", "q", 3)
    assert payload[0]["title"] == "T" and age is not None

    stale = ReconCache(base=str(tmp_path), ttl=0)
    assert stale.get("CrossrefClient", "q", 3) == (None, None)  # 즉시 만료


class _StubClient(BaseAPIClient):
    calls = 0

    async def search(self, query, max_results=3):
        _StubClient.calls += 1
        return [PaperMetadata(title="Stub", authors=["A"])]


def test_engine_cache_hit_recorded_in_report(tmp_path, monkeypatch):
    _StubClient.calls = 0
    monkeypatch.setattr(ReconEngine, "_resolve_clients",
                        lambda self, lens: [_StubClient()])

    e1 = ReconEngine(use_cache=True, cache_dir=str(tmp_path))
    asyncio.run(e1.search("inflation", lens="general"))
    assert e1.cache_report["_StubClient"]["hit"] is False
    assert _StubClient.calls == 1

    e2 = ReconEngine(use_cache=True, cache_dir=str(tmp_path))
    asyncio.run(e2.search("inflation", lens="general"))
    assert e2.cache_report["_StubClient"]["hit"] is True
    assert _StubClient.calls == 1  # 두 번째는 네트워크 호출 없음

    e3 = ReconEngine(use_cache=False, cache_dir=str(tmp_path))
    asyncio.run(e3.search("inflation", lens="general"))
    assert _StubClient.calls == 2  # --no-cache 바이패스


# ---- 3. Snowball ---------------------------------------------------------
def test_citation_client_not_in_factory_and_not_baseapi():
    # 인터페이스 오염 회피: 일반 recon 클라이언트가 아니다
    assert "citationgraph" not in CLIENT_FACTORY
    assert not issubclass(CitationGraphClient, BaseAPIClient)


def test_snowball_resolves_seed_and_parses(monkeypatch):
    def route(url, params):
        if url.endswith("/doi:10.1/seed"):
            return _Resp({"id": "https://openalex.org/W999"})
        return _Resp({"results": [
            {"title": "Citing paper", "doi": "https://doi.org/10.2/x",
             "authorships": [{"author": {"display_name": "Doe"}}]},
        ]})

    monkeypatch.setattr(
        engine_mod.httpx, "AsyncClient",
        lambda *a, **k: _FakeClient(route=route),
    )
    papers = asyncio.run(CitationGraphClient().snowball("10.1/seed"))
    assert papers and papers[0].title == "[OpenAlex] Citing paper"
    # both 방향(refs+citations) 동일 결과 → dedup으로 1건
    assert len(papers) == 1


def test_snowball_empty_doi_returns_empty():
    assert asyncio.run(CitationGraphClient().snowball("")) == []
