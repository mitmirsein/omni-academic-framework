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


# ── KCI OAI-PMH (무키 표준) ──────────────────────────────────────────────
# OAI-PMH 2.0 + Dublin Core는 고정 표준. fixture는 표준 envelope에 KCI의
# 검증된 식별자 체계(oai:kci.go.kr:ARTI/{artiId}, 사용자 실검증 2026-05)를
# 끼운 것 — 파서가 표준 경로만 쓰는지 고정한다.
import asyncio  # noqa: E402

from src.recon.engine import KciOaiClient  # noqa: E402

OAI_LISTRECORDS = """<?xml version="1.0"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
 <responseDate>2026-05-19T00:00:00Z</responseDate>
 <request verb="ListRecords" metadataPrefix="oai_dc" set="ARTI">https://open.kci.go.kr/oai/request</request>
 <ListRecords>
  <record>
   <header><identifier>oai:kci.go.kr:ARTI/ART003327481</identifier><datestamp>2024-04-17</datestamp><setSpec>ARTI</setSpec></header>
   <metadata>
    <oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
     <dc:title>Healing of Artificial Ulcers</dc:title>
     <dc:creator>임현</dc:creator>
     <dc:creator>김민수</dc:creator>
     <dc:subject>소화기암학</dc:subject>
     <dc:description>내시경 점막하 박리술로 유발된 인공 궤양의 치유와 관리에 관한 연구.</dc:description>
     <dc:identifier>ISSN:1234-5678</dc:identifier>
     <dc:identifier>10.1234/kci.2024.001</dc:identifier>
    </oai_dc:dc>
   </metadata>
  </record>
  <record>
   <header status="deleted"><identifier>oai:kci.go.kr:ARTI/ARTDELETED</identifier></header>
  </record>
 </ListRecords>
</OAI-PMH>
""".encode("utf-8")

OAI_ERROR = b"""<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
<error code="badArgument">metadataPrefix required</error></OAI-PMH>"""


def test_kci_oai_parse_standard_dc():
    papers = KciOaiClient._parse(OAI_LISTRECORDS)
    assert len(papers) == 1  # deleted 레코드는 스킵
    p = papers[0]
    assert p.title == "[KCI] Healing of Artificial Ulcers"
    assert p.authors == ["임현", "김민수"]
    assert p.abstract.startswith("내시경 점막하")
    assert p.doi == "10.1234/kci.2024.001"  # 10.x identifier만 DOI
    # 검증된 식별자 체계로 landing URL 구성
    assert p.url.endswith("ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003327481")


def test_kci_oai_error_envelope_is_graceful_empty():
    assert KciOaiClient._parse(OAI_ERROR) == []


def test_kci_oai_rejects_unknown_set_offline():
    # 잘못된 set은 네트워크 전에 차단(오프라인 안전)
    assert asyncio.run(KciOaiClient().harvest("BOGUS")) == []


def _oai_page(token: str | None) -> bytes:
    tok = f"<resumptionToken>{token}</resumptionToken>" if token else "<resumptionToken/>"
    body = (
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords>'
        '<record><header><identifier>oai:kci.go.kr:ARTI/ART%s</identifier></header>'
        '<metadata><oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:title>Rec %s</dc:title><dc:creator>A</dc:creator></oai_dc:dc></metadata></record>'
        '%s</ListRecords></OAI-PMH>'
    )
    n = token or "LAST"
    return (body % (n, n, tok)).encode("utf-8")


def test_kci_oai_follows_resumption_token(monkeypatch):
    from src.recon import engine as engine_mod

    seen_urls = []

    class _Resp:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            pass

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            seen_urls.append(url)
            if "resumptionToken=TOK1" in url:
                return _Resp(_oai_page(None))      # 2페이지: 토큰 없음 → 종료
            return _Resp(_oai_page("TOK1"))        # 1페이지: 토큰 TOK1

    monkeypatch.setattr(engine_mod.httpx, "AsyncClient", lambda *a, **k: _FakeClient())

    papers = asyncio.run(KciOaiClient().harvest("ARTI", max_records=50))
    assert len(papers) == 2  # 두 페이지 누적

    # OAI 규격: 1페이지는 metadataPrefix+set, 후속은 resumptionToken만
    assert "metadataPrefix=oai_dc" in seen_urls[0] and "set=ARTI" in seen_urls[0]
    assert "resumptionToken=TOK1" in seen_urls[1]
    assert "metadataPrefix" not in seen_urls[1] and "set=ARTI" not in seen_urls[1]


def test_kci_oai_parse_page_extracts_token():
    papers, token = KciOaiClient._parse_page(_oai_page("ABC123"))
    assert token == "ABC123" and len(papers) == 1
    _, end = KciOaiClient._parse_page(_oai_page(None))
    assert end is None  # 빈 resumptionToken = 마지막 페이지


# ── 검색어-무시 버그 수정 (GET→POST) + OAI 브리지 ──────────────────────
from src.recon.engine import PaperMetadata  # noqa: E402


def test_html_has_query_guard():
    # 검색어 미반영 응답(인기 논문 오염)은 0건 처리되도록 가드 검증
    assert KCIClient._html_has_query("<b>칼바르트 신학</b> 결과", "칼바르트 신학") is True
    assert KCIClient._html_has_query("췌장암 담도암 인기 논문", "칼바르트 신학") is False
    assert KCIClient._html_has_query("anything", "") is False


def test_kci_oai_get_record_parses_standard(monkeypatch):
    from src.recon import engine as engine_mod

    class _R:
        def __init__(self, c): self.content = c
        def raise_for_status(self): pass

    class _C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None):
            assert "verb=GetRecord" in url and "ART9" in url
            return _R(_oai_page("X").replace(b"<ListRecords>", b"<GetRecord>")
                                    .replace(b"</ListRecords>", b"</GetRecord>"))

    monkeypatch.setattr(engine_mod.httpx, "AsyncClient", lambda *a, **k: _C())
    rec = asyncio.run(KciOaiClient().get_record("ART9"))
    assert rec is not None and rec.title.startswith("[KCI]")


def test_kci_oai_get_record_blocked_returns_none(monkeypatch):
    import httpx as _httpx

    from src.recon import engine as engine_mod

    class _C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None):
            raise _httpx.RequestError("blocked")

    monkeypatch.setattr(engine_mod.httpx, "AsyncClient", lambda *a, **k: _C())
    assert asyncio.run(KciOaiClient().get_record("ART9")) is None
    assert asyncio.run(KciOaiClient().get_record("")) is None


def _web_fixture():
    return [PaperMetadata(
        title="[KCI] T", authors=["A"],
        abstract="초록 없음 (KCI 목록 미제공 — 본문은 Phase B)",
        url="https://www.kci.go.kr/x?sereArticleSearchBean.artiId=ART42",
    )]


def test_enrich_via_oai_upgrades_abstract_else_keeps(monkeypatch):
    async def fake_get(self, arti_id, *a, **k):
        assert arti_id == "ART42"
        return PaperMetadata(title="[KCI] T", authors=["A"],
                              abstract="실제 초록 본문", doi="10.1/x")

    monkeypatch.setattr(KciOaiClient, "get_record", fake_get)
    out = asyncio.run(KCIClient._enrich_via_oai(_web_fixture()))
    assert out[0].abstract == "실제 초록 본문" and out[0].doi == "10.1/x"

    # 비활성화 env → 원본 유지(새 fixture로 공유 가변 회피)
    monkeypatch.setenv("OMNI_KCI_OAI_ENRICH", "0")
    out2 = asyncio.run(KCIClient._enrich_via_oai(_web_fixture()))
    assert out2[0].abstract.startswith("초록 없음")


def test_enrich_via_oai_graceful_when_getrecord_none(monkeypatch):
    monkeypatch.delenv("OMNI_KCI_OAI_ENRICH", raising=False)

    async def none_get(self, arti_id, *a, **k):
        return None

    monkeypatch.setattr(KciOaiClient, "get_record", none_get)
    web = [PaperMetadata(title="[KCI] T", authors=["A"], abstract="초록 없음 ...",
                         url="https://kci/x?artiId=ART1")]
    out = asyncio.run(KCIClient._enrich_via_oai(web))
    assert out[0].abstract.startswith("초록 없음")  # 차단/None → 웹 필드 유지
