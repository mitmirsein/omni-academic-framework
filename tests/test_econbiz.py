from omni_academic.config.lens import get_recon_client_names, load_lens
from omni_academic.recon.engine import EconBizClient, ReconEngine

# api.econbiz.de/v1/search 실응답에서 관찰한 최소 스키마
SAMPLE = {
    "hits": {
        "hits": [
            {
                "id": "10015624793",
                "title": "Inflation targeting and risk premia in South Africa",
                "person": ["Allison, Chloë", "Wet, Theuns de"],
                "identifier_url": [
                    "https://www.resbank.co.za/.../inflation-bond-market.pdf",
                    "https://ideas.repec.org/p/rbz/wpaper/11102.html",
                ],
                "series": ["SARB working paper series ; WP, 26, 09"],
                "type": "book",
            },
            {"id": "x", "title": ""},  # 제목 없음 → 스킵되어야 함
        ]
    }
}


def test_econbiz_parse_maps_real_schema():
    papers = EconBizClient._parse(SAMPLE)
    assert len(papers) == 1
    p = papers[0]
    assert p.title.startswith("[EconBiz] Inflation targeting")
    assert p.authors == ["Allison, Chloë", "Wet, Theuns de"]
    assert p.url.endswith("inflation-bond-market.pdf")
    assert p.doi is None  # search 응답엔 DOI 없음 (검증된 한계)


def test_econbiz_parse_handles_empty():
    assert EconBizClient._parse({}) == []
    assert EconBizClient._parse({"hits": {"hits": []}}) == []


def test_economics_lens_uses_econbiz_first():
    cfg = load_lens("economics")
    assert get_recon_client_names(cfg) == ["econbiz", "crossref"]
    clients = ReconEngine()._resolve_clients("economics")
    assert isinstance(clients[0], EconBizClient)
