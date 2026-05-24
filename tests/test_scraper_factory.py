import pytest

from omni_academic.recon.scraper import (
    JinaReaderScraper,
    LightpandaScraper,
    ScraperFactory,
)


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_rejects_none_or_empty_url(bad):
    with pytest.raises(ValueError):
        ScraperFactory.get_scraper(bad)


def test_plain_url_uses_jina():
    assert isinstance(ScraperFactory.get_scraper("https://example.com/a"), JinaReaderScraper)


def test_js_heavy_domain_uses_lightpanda():
    s = ScraperFactory.get_scraper("https://www.sciencedirect.com/x")
    assert isinstance(s, LightpandaScraper)
