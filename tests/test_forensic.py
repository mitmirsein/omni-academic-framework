import asyncio

import pytest

from omni_academic.audit.forensic import ForensicAuditor, is_valid_doi_syntax
from omni_academic.recon.engine import PaperMetadata
from omni_academic.recon.scraper import LightpandaScraper


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

    async def fake_probe(self, client, url):
        return 200 if "good" in url else 404  # 'good' URL만 실존

    monkeypatch.setattr(ForensicAuditor, "_probe_status", fake_probe)

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
    assert not ForensicAuditor.passed(findings)
    assert ForensicAuditor.failed_indices(findings) == {0, 3}


@pytest.mark.parametrize("status,verdict", [
    (200, "ok"),
    (302, "ok"),
    (404, "missing"),
    (410, "missing"),
    (401, "indeterminate"),
    (403, "indeterminate"),
    (429, "indeterminate"),
    (500, "indeterminate"),
    (503, "indeterminate"),
    (400, "indeterminate"),  # 부재 증거로 보기 약한 4xx
    (None, "indeterminate"),  # 네트워크 오류
])
def test_status_classification_matrix(status, verdict):
    assert ForensicAuditor.classify_status(status) == verdict


def test_bot_blocked_doi_is_warning_not_ghost(monkeypatch):
    """403/429는 실존 부정 증거가 아니다 — 실존 인용을 차단하면 안 된다."""
    auditor = ForensicAuditor()

    async def fake_probe(self, client, url):
        return 403  # 출판사 봇 차단 시뮬레이션

    monkeypatch.setattr(ForensicAuditor, "_probe_status", fake_probe)

    papers = [PaperMetadata(
        title="paywalled", authors=["X"],
        doi="10.1234/real.but.blocked", url="https://publisher.example/p",
    )]
    findings = asyncio.run(auditor.verify_papers(papers))
    codes = {f.code for f in findings}
    assert codes == {"UNVERIFIABLE_DOI", "UNVERIFIABLE_URL"}
    assert all(f.severity == "warning" for f in findings)
    # warning이므로 HITL 후보에서 차단되지 않는다.
    assert ForensicAuditor.passed(findings)
    assert ForensicAuditor.failed_indices(findings) == set()


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
    import omni_academic.config.tools as tools
    monkeypatch.setattr(tools.shutil, "which", lambda _: None)
    out = asyncio.run(LightpandaScraper().fetch_markdown("https://x.com"))
    assert out == ""  # 하드코딩 경로 제거 — 미설정 시 정직하게 빈 문자열
    assert "mock markdown" not in out.lower()
