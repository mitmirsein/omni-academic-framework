"""라우터 모드 배선 회귀 가드 (오프라인).

`--kci-harvest` / `--snowball` 분기가 RunStore manifest에 올바른
mode/메타를 남기는지, 클라이언트를 monkeypatch해 네트워크 없이 고정.
클라이언트·파서 단위테스트는 있었으나 라우터 배선 자체는 무방비였다.
"""

import asyncio
import json

from src.recon import engine as engine_mod
from src.recon.engine import PaperMetadata
from src.store.run_store import RunStore
from src.supervisor.router import OmniSupervisorRouter


def _stop_at_hitl(monkeypatch):
    # digest 출력 후 HITL에서 'q'로 종료 → 스크래퍼/네트워크 진입 차단
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *a, **k: "q")


def _run(router, store, **kw):
    asyncio.run(router._run_recon(store, "tension", "general", no_cache=True, **kw))


def test_kci_harvest_mode_records_manifest(tmp_path, monkeypatch):
    _stop_at_hitl(monkeypatch)

    async def fake_harvest(self, set_spec="ARTI", *a, **k):
        return [PaperMetadata(title="[KCI] Harvested", authors=["임현"])]

    monkeypatch.setattr(engine_mod.KciOaiClient, "harvest", fake_harvest)

    store = RunStore.create("tension", "general", base=str(tmp_path))
    _run(OmniSupervisorRouter(), store, kci_harvest="ARTI")
    run_dir = store.finalize()

    m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["mode"] == "kci_oai_harvest"
    assert m["kci_set"] == "ARTI"
    digest = json.loads((run_dir / "digest.json").read_text(encoding="utf-8"))
    assert digest[0]["title"] == "[KCI] Harvested"


def test_snowball_mode_records_manifest(tmp_path, monkeypatch):
    _stop_at_hitl(monkeypatch)

    async def fake_snowball(self, doi, *a, **k):
        return [PaperMetadata(title="[OpenAlex] Citing", authors=["Doe"])]

    monkeypatch.setattr(engine_mod.CitationGraphClient, "snowball", fake_snowball)

    store = RunStore.create("tension", "general", base=str(tmp_path))
    _run(OmniSupervisorRouter(), store, snowball="10.1/seed")
    run_dir = store.finalize()

    m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["mode"] == "snowball"
    assert m["seed_doi"] == "10.1/seed"
    assert (run_dir / "digest.json").is_file()


def test_kci_harvest_takes_precedence_over_snowball(tmp_path, monkeypatch):
    # 두 모드 동시 지정 시 kci_harvest가 우선(분기 순서 계약 고정)
    _stop_at_hitl(monkeypatch)
    called = {"kci": False, "snow": False}

    async def fake_harvest(self, *a, **k):
        called["kci"] = True
        return [PaperMetadata(title="[KCI] X", authors=["A"])]

    async def fake_snowball(self, *a, **k):
        called["snow"] = True
        return []

    monkeypatch.setattr(engine_mod.KciOaiClient, "harvest", fake_harvest)
    monkeypatch.setattr(engine_mod.CitationGraphClient, "snowball", fake_snowball)

    store = RunStore.create("tension", "general", base=str(tmp_path))
    _run(OmniSupervisorRouter(), store, kci_harvest="JOUR", snowball="10.1/seed")
    store.finalize()

    assert called["kci"] is True and called["snow"] is False
    assert store._meta["mode"] == "kci_oai_harvest"


def test_default_keyword_mode_when_no_special_flags(tmp_path, monkeypatch):
    _stop_at_hitl(monkeypatch)

    async def fake_search(self, query, lens="general"):
        return [PaperMetadata(title="[Crossref] Kw", authors=["A"])]

    monkeypatch.setattr(engine_mod.ReconEngine, "search", fake_search)

    store = RunStore.create("tension", "general", base=str(tmp_path))
    _run(OmniSupervisorRouter(), store)
    store.finalize()

    # 기본 키워드 경로는 mode 노트를 남기지 않는다(특수 모드만 표식)
    assert "mode" not in store._meta
    assert (store.dir / "digest.json").is_file()
