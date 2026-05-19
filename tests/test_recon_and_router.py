from src.recon.engine import PaperMetadata, ReconEngine
from src.supervisor.router import _resolve_document


def test_noise_filter_drops_editorial_keeps_substring_safe():
    engine = ReconEngine()
    papers = [
        PaperMetadata(title="Editorial: welcome", authors=["X"]),
        PaperMetadata(title="Index Theory in Topology", authors=["Y"]),
    ]
    clean = engine._smart_noise_filter(papers)
    titles = [p.title for p in clean]
    assert "Editorial: welcome" not in titles
    assert "Index Theory in Topology" in titles  # 'index' 부분문자열 오탐 금지


def test_resolve_document_reads_file(tmp_path):
    f = tmp_path / "paper.md"
    f.write_text("real content", encoding="utf-8")
    assert _resolve_document(str(f)) == "real content"


def test_resolve_document_inline_passthrough():
    assert _resolve_document("not a path, just a query") == "not a path, just a query"
