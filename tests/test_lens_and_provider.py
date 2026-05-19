import pytest

from src.config.lens import (
    LensNotFoundError,
    get_recon_client_names,
    load_lens,
)
from src.llm.provider import AnthropicProvider
from src.recon.engine import ArxivClient, CrossrefClient, ReconEngine


def test_load_lens_reads_yaml():
    cfg = load_lens("cs")
    assert cfg["name"] == "Computer Science"
    assert get_recon_client_names(cfg) == ["arxiv", "crossref"]


def test_load_lens_missing_raises():
    with pytest.raises(LensNotFoundError):
        load_lens("does-not-exist")


def test_recon_clients_are_config_driven():
    engine = ReconEngine()
    clients = engine._resolve_clients("cs")
    types = {type(c) for c in clients}
    assert ArxivClient in types and CrossrefClient in types


def test_recon_unknown_lens_falls_back_to_general():
    engine = ReconEngine()
    clients = engine._resolve_clients("nonexistent-domain")
    # general.yaml → crossref
    assert any(isinstance(c, CrossrefClient) for c in clients)


def test_anthropic_provider_requires_api_key():
    # 빈 키는 설정 오류 → ValueError (router가 --mock 안내와 함께 처리)
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="")
