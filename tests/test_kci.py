from src.recon.engine import KCIClient

# KCI OpenAPI 실응답 양식을 모사한 가상의 XML Fixture
SAMPLE_KCI_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <record>
    <articleInfo>
      <title-group>
        <article-title>A Study on Theological Tension</article-title>
      </title-group>
      <abstract-group>
        <abstract>This paper analyzes the tension between Barth and Calvin.</abstract>
      </abstract-group>
      <url>https://www.kci.go.kr/article/12345</url>
    </articleInfo>
    <author-group>
      <author>Kim, Min-su</author>
      <author>Lee, Young-hee</author>
    </author-group>
  </record>
  <record>
    <articleInfo>
      <title-group>
        <article-title></article-title>
      </title-group>
    </articleInfo>
  </record>
</metadata>
"""

def test_kci_parse_maps_real_xml_schema():
    papers = KCIClient._parse(SAMPLE_KCI_XML)
    assert len(papers) == 2
    
    # 첫 번째 논문 검증
    p1 = papers[0]
    assert p1.title == "[KCI] A Study on Theological Tension"
    assert p1.authors == ["Kim, Min-su", "Lee, Young-hee"]
    assert p1.abstract == "This paper analyzes the tension between Barth and Calvin."
    assert p1.url == "https://www.kci.go.kr/article/12345"
    assert p1.doi is None

    # 두 번째 논문 검증 (누락 정보에 대한 기본값 융합 검증)
    p2 = papers[1]
    assert p2.title == "[KCI] 제목 없음"
    assert p2.authors == ["저자 미상"]
    assert p2.abstract == "초록 없음"
    assert p2.url is None

def test_kci_parse_handles_invalid_xml():
    # 파싱 불가능한 깨진 XML에 대해 빈 목록을 반환하며 죽지 않는지 검증
    papers = KCIClient._parse(b"<broken><xml>")
    assert papers == []


# KCI 실 응답이 네임스페이스를 달고 올 가능성(실 샘플 미확보) 대비 변형 fixture.
NAMESPACED_KCI_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kci:metadata xmlns:kci="http://www.kci.go.kr/ns">
  <kci:record>
    <kci:articleInfo>
      <kci:title-group><kci:article-title>Namespaced Title</kci:article-title></kci:title-group>
      <kci:url>https://www.kci.go.kr/article/99999</kci:url>
    </kci:articleInfo>
    <kci:author-group><kci:author>Park, Ji-won</kci:author></kci:author-group>
  </kci:record>
</kci:metadata>
"""

# records가 아닌 에러 봉투를 돌려주는 경우(권한/쿼터 등) — graceful empty.
ERROR_ENVELOPE_XML = b"""<?xml version="1.0"?><error><code>401</code><message>unauthorized</message></error>"""


def test_kci_parse_is_namespace_tolerant():
    papers = KCIClient._parse(NAMESPACED_KCI_XML)
    assert len(papers) == 1
    assert papers[0].title == "[KCI] Namespaced Title"
    assert papers[0].authors == ["Park, Ji-won"]
    assert papers[0].url == "https://www.kci.go.kr/article/99999"


def test_kci_parse_error_envelope_is_graceful_empty():
    assert KCIClient._parse(ERROR_ENVELOPE_XML) == []
