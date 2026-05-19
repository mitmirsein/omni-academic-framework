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


def test_lightpanda_returns_empty_on_failure_not_fake(monkeypatch):
    # 실 lightpanda 바이너리 연동: 실패 시 가짜 마크다운이 아니라 빈 문자열을
    # 반환해야 한다(환각 차단 원칙). subprocess는 모킹해 오프라인 보장.
    async def fake_exec(*args, **kwargs):
        class _P:
            returncode = 1

            async def communicate(self):
                return b"", b"binary not available"

        return _P()

    # OMNI_LIGHTPANDA_BIN을 세팅해 resolve_tool 통과 → subprocess 실패 경로 검증
    monkeypatch.setenv("OMNI_LIGHTPANDA_BIN", "lightpanda-fake")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    out = asyncio.run(LightpandaScraper().fetch_markdown("https://x.com"))
    assert out == ""


def test_lightpanda_unset_fails_honestly(monkeypatch):
    monkeypatch.delenv("OMNI_LIGHTPANDA_BIN", raising=False)
    import src.config.tools as tools
    monkeypatch.setattr(tools.shutil, "which", lambda _: None)
    out = asyncio.run(LightpandaScraper().fetch_markdown("https://x.com"))
    assert out == ""  # 하드코딩 경로 제거 — 미설정 시 정직하게 빈 문자열
    assert "mock markdown" not in out.lower()
