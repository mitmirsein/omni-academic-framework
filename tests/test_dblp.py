from src.config.lens import get_recon_client_names, load_lens
from src.recon.engine import DBLPClient, ReconEngine

# dblp.org/search/publ/api?format=json 실응답에서 관찰한 최소 스키마.
# 다건 결과 → hit/author 모두 list.
DBLP_MULTI = {
    "result": {
        "status": {"@code": "200", "text": "OK"},
        "hits": {
            "@total": "48507",
            "@sent": "2",
            "hit": [
                {
                    "@id": "314230",
                    "info": {
                        "authors": {"author": [
                            {"@pid": "216/3953", "text": "Sangyeob Kim"},
                            {"@pid": "37/2676", "text": "Hoi-Jun Yoo"},
                        ]},
                        "title": "C-Transformer: An Energy-Efficient Processor.",
                        "venue": "IEEE J. Solid State Circuits",
                        "year": "2025",
                        "type": "Journal Articles",
                        "doi": "10.1109/JSSC.2025.3554699",
                        "ee": "https://doi.org/10.1109/JSSC.2025.3554699",
                        "url": "https://dblp.org/rec/journals/jssc/KimKJKHLLY25",
                    },
                },
                {"@id": "999", "info": {"title": ""}},  # 제목 없음 → 스킵
            ],
        },
    }
}

# 단건 결과 → DBLP는 hit을 list가 아닌 단일 객체로 직렬화하는 변덕.
# 저자도 1명이면 author가 단일 객체. abstract는 미제공.
DBLP_SINGLE = {
    "result": {
        "hits": {
            "@total": "1",
            "@sent": "1",
            "hit": {
                "@id": "1",
                "info": {
                    "authors": {"author": {"@pid": "x/1", "text": "Solo Author"}},
                    "title": "A Single-Result Paper.",
                    "venue": "ArbitraryConf",
                    "year": "2020",
                    "url": "https://dblp.org/rec/conf/x/Solo20",
                },
            },
        }
    }
}


def test_dblp_parse_multi_real_schema():
    papers = DBLPClient._parse(DBLP_MULTI)
    assert len(papers) == 1  # 빈 제목 레코드는 스킵
    p = papers[0]
    assert p.title == "[DBLP] C-Transformer: An Energy-Efficient Processor."
    assert p.authors == ["Sangyeob Kim", "Hoi-Jun Yoo"]
    assert p.doi == "10.1109/JSSC.2025.3554699"
    assert p.url == "https://doi.org/10.1109/JSSC.2025.3554699"  # ee 우선
    assert p.venue == "IEEE J. Solid State Circuits"
    assert "DBLP" in p.abstract  # DBLP는 abstract 미제공 → 정직한 표기


def test_dblp_normalizes_single_hit_and_single_author():
    """항목 1개일 때 list가 아닌 단일 객체로 오는 변덕을 정규화한다."""
    papers = DBLPClient._parse(DBLP_SINGLE)
    assert len(papers) == 1
    p = papers[0]
    assert p.title == "[DBLP] A Single-Result Paper."
    assert p.authors == ["Solo Author"]
    assert p.doi is None
    assert p.url == "https://dblp.org/rec/conf/x/Solo20"  # ee 없으면 url 폴백


def test_dblp_handles_missing_hits_and_authors():
    assert DBLPClient._parse({}) == []
    assert DBLPClient._parse({"result": {"hits": {"@sent": "0"}}}) == []
    # authors 키 자체가 없는 레코드도 크래시 없이 '저자 미상'.
    out = DBLPClient._parse(
        {"result": {"hits": {"hit": {"info": {"title": "No Authors Here."}}}}}
    )
    assert out[0].authors == ["저자 미상"]


def test_cs_lens_now_routes_dblp():
    assert get_recon_client_names(load_lens("cs")) == ["arxiv", "dblp", "crossref"]
    eng = ReconEngine()
    assert isinstance(eng._resolve_clients("cs")[1], DBLPClient)
