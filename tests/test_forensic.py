import asyncio

import pytest

from src.audit.forensic import ForensicAuditor, is_valid_doi_syntax
from src.recon.engine import PaperMetadata
from src.recon.scraper import LightpandaScraper


@pytest.mark.parametrize("doi,ok", [
    ("10.1234/abc.def", True),
    ("10.1038/s41586-020-2649-2", True),
    ("not-a-doi", False),
    ("10.1234/crossref.dummy", True),   # 문법은 valid → 실존 ping이 거른다
    ("", False),
    (None, False),
])
def test_doi_syntax(doi, ok):
    assert is_valid_doi_syntax(doi) is ok


def test_forensic_flags_ghost_doi_and_dead_url(monkeypatch):
    auditor = ForensicAuditor()

    async def fake_resolves(self, client, url):
        return "good" in url  # only URLs containing 'good' resolve

    monkeypatch.setattr(ForensicAuditor, "_resolves", fake_resolves)

    papers = [
        PaperMetadata(title="ghost", authors=["X"], doi="10.9999/bad.ref"),
        PaperMetadata(title="deadlink", authors=["Y"], url="https://bad.example/x"),
        PaperMetadata(title="nolocator", authors=["Z"]),
        PaperMetadata(title="malformed", authors=["W"], doi="nope"),
    ]
    findings = asyncio.run(auditor.verify_papers(papers))
    codes = {f.code for f in findings}
    assert "GHOST_DOI" in codes
    assert "DEAD_URL" in codes
    assert "NO_LOCATOR" in codes
    assert "MALFORMED_DOI" in codes


def test_lightpanda_is_honest_blueprint():
    with pytest.raises(NotImplementedError):
        asyncio.run(LightpandaScraper().fetch_markdown("https://x.com"))
