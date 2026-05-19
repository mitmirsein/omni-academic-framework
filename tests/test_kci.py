"""KCI 어댑터 테스트.

정직성 주의: KCI Open API는 `key` 파라미터가 필수이며, 실 API 검증
(2026-05) 결과 루트는 `<MetaData>`, 키 누락 시
`outputData/result/resultMsg`에 에러가 온다. 키는 일반 사용자에게
열려 있지 않다(기관/제한). 따라서 아래 record fixture는 KCI의 검증된
실 스키마가 아니라 **휴리스틱(local-name) 추출 계약을 고정하는 가정용
fixture**다. 검증된 것은 에러-봉투 경로뿐이다.
"""

from src.recon.engine import KCIClient

# ✅ 실 API에서 그대로 캡처한 응답(키 누락) — 검증된 구조.
REAL_NO_KEY_ENVELOPE = b"""<?xml version="1.0" encoding="UTF-8"?>
<MetaData>
  <inputData><apiCode>articleSearch</apiCode><title><![CDATA[theology]]></title></inputData>
  <outputData><result><resultMsg>\xed\x95\x84\xec\x88\x98 \xec\x9a\x94\xec\xb2\xad \xed\x8c\x8c\xeb\x9d\xbc\xeb\xaf\xb8\xed\x84\xb0\xea\xb0\x80 \xec\x97\x86\xec\x9d\x8c =&gt; key</resultMsg></result></outputData>
</MetaData>
"""

# ⚠️ 가정용(미검증): KCI record 필드 스키마는 키드 샘플 미확보로 불명.
# local-name 휴리스틱이 임의 중첩에서 title/author/url을 뽑는지만 고정한다.
ASSUMED_RECORD_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<MetaData><outputData>
  <record>
    <article-title>A Study on Theological Tension</article-title>
    <author>Kim, Min-su</author>
    <author>Lee, Young-hee</author>
    <url>https://www.kci.go.kr/article/12345</url>
    <abstract>Tension between Barth and Calvin.</abstract>
  </record>
  <record><article-title></article-title></record>
</outputData></MetaData>
"""

NAMESPACED_RECORD_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kci:MetaData xmlns:kci="http://kci/ns"><kci:outputData>
  <kci:record><kci:title>Namespaced Title</kci:title>
  <kci:author>Park, Ji-won</kci:author>
  <kci:url>https://www.kci.go.kr/article/99999</kci:url></kci:record>
</kci:outputData></kci:MetaData>
"""


def test_kci_real_no_key_envelope_is_graceful_empty():
    # 검증된 실 구조: 키 누락 → 레코드 0 → 정직하게 빈 결과(조용한 [] 아님).
    assert KCIClient._parse(REAL_NO_KEY_ENVELOPE) == []


def test_kci_heuristic_record_extraction_contract():
    papers = KCIClient._parse(ASSUMED_RECORD_XML)
    assert len(papers) == 2
    p = papers[0]
    assert p.title == "[KCI] A Study on Theological Tension"
    assert p.authors == ["Kim, Min-su", "Lee, Young-hee"]
    assert p.url == "https://www.kci.go.kr/article/12345"
    assert papers[1].title == "[KCI] 제목 없음"
    assert papers[1].authors == ["저자 미상"]


def test_kci_namespace_tolerant():
    papers = KCIClient._parse(NAMESPACED_RECORD_XML)
    assert len(papers) == 1
    assert papers[0].title == "[KCI] Namespaced Title"
    assert papers[0].authors == ["Park, Ji-won"]


def test_kci_invalid_xml_is_graceful_empty():
    assert KCIClient._parse(b"<broken><xml>") == []


# ✅ 실 lightpanda 렌더 DOM(2026-05 캡처)에서 축약한 검증된 구조 스냅샷.
# 구조 변화 시 이 테스트가 먼저 실패한다.
import pytest  # noqa: E402

pytest.importorskip("bs4")

REAL_RENDERED_FRAGMENT = """
<table class="search-list"><tbody>
<tr><td class="checkpoint"></td><td>1 .</td><td>
  <div class="s-state-type-ico">KCI 등재</div>
  <a href="/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003327481" class="subject"> Healing of Artificial Ulcers </a>
  <ul class="nopm floats subject-info">
    <li><a href="/kciportal/po/citationindex/poCretDetail.kci?citationBean.cretId=CRT001665022">임현</a>
        <a href="https://orcid.org/0000-0001-6581-6420"><i class="fab fa-orcid"></i></a></li>
    <li><a href="/kciportal/po/search/poInsiSearSoceView.kci?insiGeneInfoBean.insiId=INS000058973">대한소화기암연구학회</a></li>
    <li><a href="/kciportal/ci/seriesSearch/ciSereInfoView.kci?sereSearBean.sereId=SER01">대한소화기암학회지</a></li>
  </ul>
</td></tr>
<tr><td class="checkpoint"></td><td>2 .</td><td>
  <a href="/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART000000002" class="subject"> A Theology of Tension </a>
  <ul class="subject-info">
    <li><a href="/kciportal/po/citationindex/poCretDetail.kci?citationBean.cretId=CRT2">김민수</a></li>
    <li><a href="/kciportal/ci/seriesSearch/ciSereInfoView.kci?sereSearBean.sereId=SER02">한국조직신학논총</a></li>
  </ul>
</td></tr>
</tbody></table>
"""


def test_kci_html_snapshot_verified_selectors():
    papers = KCIClient._parse_html(REAL_RENDERED_FRAGMENT, max_results=5)
    assert len(papers) == 2
    p = papers[0]
    assert p.title == "[KCI] Healing of Artificial Ulcers"
    assert p.url == "https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003327481"
    assert p.authors == ["임현"]  # orcid 링크는 제외, poCretDetail만
    assert p.venue == "대한소화기암연구학회"  # 첫 매칭(institution/series)
    assert p.abstract.startswith("초록 없음")  # 목록뷰 무초록 — 정직 표기
    assert papers[1].title == "[KCI] A Theology of Tension"
    assert papers[1].authors == ["김민수"]


def test_kci_html_respects_max_results():
    assert len(KCIClient._parse_html(REAL_RENDERED_FRAGMENT, max_results=1)) == 1


def test_kci_html_empty_is_graceful():
    assert KCIClient._parse_html("<html><body>no results</body></html>", 5) == []
