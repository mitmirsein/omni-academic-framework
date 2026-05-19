from src.config.lens import get_recon_client_names, load_lens
from src.recon.engine import OpenAlexClient, PubMedClient, ReconEngine

# eutils esummary.fcgi (retmode=json) 실응답에서 관찰한 최소 스키마
PUBMED_SUMMARY = {
    "result": {
        "uids": ["38000000", "999"],
        "38000000": {
            "uid": "38000000",
            "title": "Ethical dilemmas in in vitro fertilization.",
            "authors": [{"name": "Reguera Cabezas M"}],
            "source": "Salud Colect",
            "articleids": [
                {"idtype": "pubmed", "value": "38000000"},
                {"idtype": "doi", "value": "10.18294/sc.2023.4462"},
            ],
        },
        "999": {"uid": "999", "title": ""},  # 제목 없음 → 스킵
    }
}

# api.openalex.org/works 실응답에서 관찰한 최소 스키마
OPENALEX = {
    "results": [
        {
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.1000/xyz",
            "title": "How to Read Karl Barth",
            "publication_year": 1990,
            "primary_location": {
                "landing_page_url": "https://example.org/barth",
                "source": {"display_name": "OUP"},
            },
            "authorships": [{"author": {"display_name": "George Hunsinger"}}],
            "cited_by_count": 42,
            "abstract_inverted_index": {"Barth": [0], "theology": [1]},
        },
        {"title": "", "display_name": ""},  # 스킵
    ]
}


def test_pubmed_parse_maps_real_schema():
    papers = PubMedClient._parse(PUBMED_SUMMARY)
    assert len(papers) == 1
    p = papers[0]
    assert p.title.startswith("[PubMed] Ethical dilemmas")
    assert p.doi == "10.18294/sc.2023.4462"
    assert p.url == "https://pubmed.ncbi.nlm.nih.gov/38000000/"
    assert p.venue == "Salud Colect"


def test_openalex_parse_and_abstract_reconstruction():
    papers = OpenAlexClient._parse(OPENALEX)
    assert len(papers) == 1
    p = papers[0]
    assert p.title == "[OpenAlex] How to Read Karl Barth"
    assert p.doi == "10.1000/xyz"  # https://doi.org/ 접두 제거
    assert p.abstract == "Barth theology"  # inverted-index 정렬 복원
    assert p.citation_count == 42
    assert p.authors == ["George Hunsinger"]


def test_openalex_handles_missing_abstract_and_source():
    out = OpenAlexClient._parse({"results": [{"title": "X"}]})
    assert out[0].abstract == "초록 없음"
    assert out[0].venue is None


def test_lens_blind_spots_now_covered():
    assert get_recon_client_names(load_lens("medical")) == ["pubmed", "crossref"]
    assert get_recon_client_names(load_lens("theology")) == ["openalex", "kci", "crossref"]
    assert get_recon_client_names(load_lens("humanities")) == ["openalex", "kci", "crossref"]
    eng = ReconEngine()
    assert isinstance(eng._resolve_clients("medical")[0], PubMedClient)
    assert isinstance(eng._resolve_clients("theology")[0], OpenAlexClient)
