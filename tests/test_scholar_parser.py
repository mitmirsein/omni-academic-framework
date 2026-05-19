"""Google Scholar HTML 파서 snapshot 회귀 가드.

Scholar HTML 구조 변화는 _parse_scholar_html을 조용히 깨뜨린다. 아래
SNAPSHOT은 파서가 의존하는 셀렉터(.gs_r.gs_or.gs_scl / .gs_rt a /
.gs_a / .gs_rs / .gs_fl a "Cited by N")를 고정한다. 구조 가정이
바뀌면 이 테스트가 먼저 실패해야 한다.
"""

import pytest

pytest.importorskip("bs4")  # scholar-browser extra; CI는 해당 extra로 구동

from src.recon.engine import SerpApiScholarClient  # noqa: E402

SNAPSHOT = """
<html><body>
<div class="gs_r gs_or gs_scl">
  <div class="gs_ri">
    <h3 class="gs_rt"><a href="https://example.org/barth.pdf">[PDF] How to Read Karl Barth</a></h3>
    <div class="gs_a">G Hunsinger, K Barth - Oxford University Press, 1991 - example.org</div>
    <div class="gs_rs">A study of Barth's dogmatic method and its hermeneutic shape.</div>
    <div class="gs_fl"><a href="#">Cited by 357</a><a href="#">Related articles</a></div>
  </div>
</div>
<div class="gs_r gs_or gs_scl">
  <div class="gs_ri">
    <h3 class="gs_rt"><a href="https://example.org/inflation">Inflation Targeting and Risk Premia</a></h3>
    <div class="gs_a">C Allison, T de Wet - SARB Working Paper, 2026 - resbank.co.za</div>
    <div class="gs_rs">Decomposition of bond yields into inflation risk premia.</div>
    <div class="gs_fl"><a href="#">Cited by 4</a></div>
  </div>
</div>
</body></html>
"""


def test_scholar_parser_snapshot():
    papers = SerpApiScholarClient()._parse_scholar_html(SNAPSHOT, max_results=5)
    assert len(papers) == 2

    a = papers[0]
    # [PDF] 접두는 제거, 출처 태그 [Google Scholar]는 부착(타 클라이언트와 일관)
    assert a.title == "[Google Scholar] How to Read Karl Barth"
    assert a.url == "https://example.org/barth.pdf"
    assert a.authors == ["G Hunsinger", "K Barth"]
    # 현 파서는 .gs_a의 두 번째 토큰을 그대로 venue로 쓴다(연도 포함) —
    # snapshot은 이 실제 동작을 고정한다(원하면 후속 개선 대상).
    assert a.venue == "Oxford University Press, 1991"
    assert "dogmatic method" in a.abstract
    assert a.citation_count == 357

    b = papers[1]
    assert b.title == "[Google Scholar] Inflation Targeting and Risk Premia"
    assert b.citation_count == 4


def test_scholar_parser_respects_max_results():
    papers = SerpApiScholarClient()._parse_scholar_html(SNAPSHOT, max_results=1)
    assert len(papers) == 1


def test_scholar_parser_empty_html_is_honest_empty():
    assert SerpApiScholarClient()._parse_scholar_html("<html></html>", 5) == []
