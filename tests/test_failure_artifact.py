import json

from omni_academic.store.run_store import RunStore


def test_failure_artifact_written_and_truncated(tmp_path):
    store = RunStore.create("q", "general", mock=True, base=str(tmp_path))
    store.write_failure_artifact({
        "stage": "scraping",
        "url": "https://example.org/x.pdf",
        "scraper": "PdfExtractorScraper",
        "http_status": 403,
        "content_type": "text/html",
        "raw_excerpt": "Z" * 2000,
        "error_message": "scraper returned empty markdown",
    })
    run_dir = store.finalize()

    data = json.loads((run_dir / "failure.json").read_text(encoding="utf-8"))
    assert data["stage"] == "scraping"
    assert data["http_status"] == 403
    assert data["scraper"] == "PdfExtractorScraper"
    assert data["raw_excerpt"].endswith("...(truncated)")
    assert len(data["raw_excerpt"]) <= 820  # 800 + 표식
    assert "recorded_at" in data

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("has_failure_artifact") is True
    assert "failure.json" in manifest.get("artifacts", [])


def test_report_references_failure_artifact(tmp_path):
    store = RunStore.create("q", "general", mock=True, base=str(tmp_path))
    store.note("status", "scraping_failed")
    store.write_failure_artifact({"stage": "scraping", "url": "u", "scraper": "X"})
    run_dir = store.finalize()
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "Failure Diagnostics" in report
    assert "failure.json" in report
