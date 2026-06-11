"""Phase 3 — 피어 리뷰 패널 유닛 및 통합 테스트 (test_peer_review.py)"""

import json

import pytest

from omni_academic.analyze.peer_review import PeerReviewPanel, ReviewReport
from omni_academic.draft.scribe import DraftClaim, DraftReport, DraftSection
from omni_academic.llm.provider import MockProvider
from omni_academic.supervisor import router as router_mod
from omni_academic.supervisor.router import ModuleType, OmniSupervisorRouter, RouterRequest


class AlwaysBadReviewProvider:
    last_usage = None

    def generate_structured_output(self, prompt, schema):
        self.last_usage = {"model": "bad-review", "mock": True, "schema": schema.__name__}
        return schema.model_validate({
            "reviews": [
                {
                    "panelist": "Ella",
                    "score": 95,
                    "feedback": "Ungrounded praise.",
                    "source_quotes": ["this quote is not in the draft"],
                }
            ],
            "editor_decision": "Accept",
            "editor_summary": "Looks good despite bad grounding.",
            "final_score": 95,
        })


class CorrectingReviewProvider:
    def __init__(self):
        self.calls = 0
        self.last_usage = None

    def generate_structured_output(self, prompt, schema):
        self.calls += 1
        self.last_usage = {
            "model": "correcting-review",
            "mock": True,
            "schema": schema.__name__,
            "calls": self.calls,
        }
        quote = (
            "this quote is not in the draft"
            if self.calls == 1
            else "vere Deus et vere homo"
        )
        return schema.model_validate({
            "reviews": [
                {
                    "panelist": "Ella",
                    "score": 88,
                    "feedback": "Corrected on retry.",
                    "source_quotes": [quote],
                }
            ],
            "editor_decision": "Accept",
            "editor_summary": "Grounded after retry.",
            "final_score": 88,
        })


@pytest.fixture
def sample_draft() -> DraftReport:
    return DraftReport(
        title="Aporia and Christology",
        thesis="The two natures of Christ must be held in paradoxical tension.",
        sections=[
            DraftSection(
                section_type="introduction",
                heading="Introduction",
                body="The early councils affirmed that Christ is vere Deus et vere homo [C1]. This constitutes a profound paradox.",
                claim_ids=["C1"]
            )
        ],
        claims=[
            DraftClaim(
                claim_id="C1",
                paragraph_id="P_0001",
                source_quote="vere Deus et vere homo",
                node_id=None
            )
        ],
        open_tensions=["Irreducible paradox of dual natures."]
    )


def test_peer_review_panel_loads_config():
    panel = PeerReviewPanel()
    cfg = panel._load_panel_config()
    assert cfg["name"] == "Academic Peer Review Panel"
    names = {p["name"] for p in cfg["panelists"]}
    assert {"Ella", "Miranda", "Methodologist", "Devil's Advocate"} <= names
    assert cfg["chief_editor"]["name"] == "Chief Editor"


def test_verify_review_grounding_success(sample_draft):
    report = ReviewReport(
        reviews=[
            {
                "panelist": "Ella",
                "score": 90,
                "feedback": "Great thesis.",
                "source_quotes": ["vere Deus et vere homo", "Aporia and Christology"]
            }
        ],
        editor_decision="Accept",
        editor_summary="Good.",
        final_score=90
    )
    # 텍스트에 포함되어 있으므로 통과해야 함
    PeerReviewPanel._verify_review_grounding(report, sample_draft)


def test_verify_review_grounding_failure(sample_draft):
    report = ReviewReport(
        reviews=[
            {
                "panelist": "Ella",
                "score": 90,
                "feedback": "Great thesis.",
                "source_quotes": ["hallucinated quote that does not exist in the draft"]
            }
        ],
        editor_decision="Accept",
        editor_summary="Good.",
        final_score=90
    )
    with pytest.raises(ValueError, match="referenced a source quote that is absent"):
        PeerReviewPanel._verify_review_grounding(report, sample_draft)


def test_build_review_with_mock_provider(sample_draft):
    panel = PeerReviewPanel()
    provider = MockProvider()
    report = panel.build_review(sample_draft, "theology", provider)
    assert report.final_score == 87
    assert report.editor_decision == "Accept"
    assert len(report.reviews) == 4
    # MockProvider가 정확히 드래프트에서 본문을 파싱해 냈는지
    for rev in report.reviews:
        assert rev.source_quotes[0] in (
            "Aporia and Christology",
            "The two natures of Christ must be held in paradoxical tension.",
            "vere Deus et vere homo"
        )


def test_build_review_hard_fails_after_grounding_retries(sample_draft):
    panel = PeerReviewPanel()
    with pytest.raises(ValueError, match="Peer review grounding failed after 2 attempt"):
        panel.build_review(sample_draft, "theology", AlwaysBadReviewProvider())
    assert panel.last_attempts == 2


def test_build_review_can_recover_on_second_attempt(sample_draft):
    panel = PeerReviewPanel()
    provider = CorrectingReviewProvider()
    report = panel.build_review(sample_draft, "theology", provider)
    assert provider.calls == 2
    assert panel.last_attempts == 2
    assert report.reviews[0].source_quotes == ["vere Deus et vere homo"]


def test_render_review(sample_draft):
    panel = PeerReviewPanel()
    provider = MockProvider()
    report = panel.build_review(sample_draft, "theology", provider)
    md = panel.render_review(report)
    assert "# Academic Peer Review Report" in md
    assert "Editor-in-Chief Verdict:" in md
    assert "Reviewer: **Ella**" in md
    assert "Reviewer: **Devil's Advocate**" in md


@pytest.mark.anyio
async def test_router_review_mode_mock(tmp_path):
    # E2E 검증용 임시 런 디렉터리 구성
    run_dir = tmp_path / "runs" / "test-query" / "mock-run"
    run_dir.mkdir(parents=True)
    
    # 1. draft.json & fulltext.md 모의 생성
    draft_report = DraftReport(
        title="CS Scale Test",
        thesis="Mock CS thesis.",
        sections=[
            DraftSection(
                section_type="introduction",
                heading="Introduction",
                body="This is a test run for peer review [C1].",
                claim_ids=["C1"]
            )
        ],
        claims=[
            DraftClaim(
                claim_id="C1",
                paragraph_id="P_0001",
                source_quote="test run for peer review",
                node_id=None
            )
        ]
    )
    (run_dir / "draft.json").write_text(draft_report.model_dump_json(), encoding="utf-8")
    (run_dir / "fulltext.md").write_text("This is a test run for peer review.", encoding="utf-8")
    
    # manifest.json 모의 생성
    import json
    manifest = {
        "run_id": "test-query/mock-run",
        "created_at": "2026-05-24T12:00:00Z",
        "query": "CS Scale Test",
        "lens": "cs",
        "mock": True,
        "status": "completed",
        "draft_passed": True,
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # 라우터 가동
    runs_base = tmp_path / "output-runs"
    router = OmniSupervisorRouter(use_mock=True, runs_base=str(runs_base))
    req = RouterRequest(
        query=str(run_dir),
        lens="cs",
        target_module=ModuleType.REVIEW,
        use_mock=True
    )
    
    # Router가 Runs 폴더에 저장할 경로를 임시 폴더로 잡도록 base path 조정 (mock config env injection 생략하고 직접 store mock 처리 가능)
    # 여기서는 build_review + write_review 가 정상 완주하는지 실행
    await router.route(req)

    review_jsons = list(runs_base.rglob("review.json"))
    assert len(review_jsons) == 1
    run_out = review_jsons[0].parent
    assert (run_out / "review.md").is_file()
    out_manifest = json.loads((run_out / "manifest.json").read_text(encoding="utf-8"))
    assert out_manifest["status"] == "completed"
    assert out_manifest["review_grounding_passed"] is True
    assert out_manifest["review_passed"] is True
    assert out_manifest["review_score"] == 87
    assert out_manifest["llm_usage"]["review"]["mock"] is True
    assert out_manifest["llm_usage"]["review_attempts"] == 1
    assert out_manifest["artifact_manifest"]["review.json"]["exists"] is True
    assert "### Peer Review Panel" in (run_out / "report.md").read_text(encoding="utf-8")
    # 출처 체인(Chain of Custody) 기록
    assert out_manifest["source_provenance"] == "manifest"
    assert out_manifest["source_run_id"] == "test-query/mock-run"
    assert out_manifest["source_draft_passed"] is True
    assert out_manifest["source_mock"] is True


@pytest.mark.anyio
async def test_router_review_grounding_failure_blocks_artifact(tmp_path, monkeypatch):
    run_dir = tmp_path / "runs" / "test-query" / "mock-run"
    run_dir.mkdir(parents=True)
    draft_report = DraftReport(
        title="CS Scale Test",
        thesis="Mock CS thesis.",
        sections=[
            DraftSection(
                section_type="introduction",
                heading="Introduction",
                body="This is a test run for peer review [C1].",
                claim_ids=["C1"],
            )
        ],
        claims=[
            DraftClaim(
                claim_id="C1",
                paragraph_id="P_0001",
                source_quote="test run for peer review",
                node_id=None,
            )
        ],
    )
    (run_dir / "draft.json").write_text(draft_report.model_dump_json(), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({
            "run_id": "test-query/mock-run",
            "query": "CS Scale Test",
            "mock": True,
            "draft_passed": True,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        router_mod,
        "_make_provider",
        lambda use_mock: AlwaysBadReviewProvider(),
    )

    runs_base = tmp_path / "output-runs"
    router = OmniSupervisorRouter(use_mock=True, runs_base=str(runs_base))
    await router.route(RouterRequest(
        query=str(run_dir),
        lens="cs",
        target_module=ModuleType.REVIEW,
        use_mock=True,
    ))

    manifests = list(runs_base.rglob("manifest.json"))
    assert len(manifests) == 1
    run_out = manifests[0].parent
    out_manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert out_manifest["status"] == "blocked_by_review_grounding"
    assert out_manifest["review_grounding_passed"] is False
    assert out_manifest["review_passed"] is False
    assert out_manifest["llm_usage"]["review_attempts"] == 2
    assert (run_out / "failure.json").is_file()
    assert not (run_out / "review.json").exists()
    assert not (run_out / "review.md").exists()


@pytest.mark.anyio
async def test_router_review_blocked_when_source_draft_failed(tmp_path):
    """감사 반려된 draft run은 리뷰 입력으로 쓸 수 없다 (출처 체인, F1)."""
    run_dir = tmp_path / "runs" / "bad-draft" / "mock-run"
    run_dir.mkdir(parents=True)
    draft_report = DraftReport(
        title="Blocked Draft",
        thesis="This draft failed its compliance audit.",
        sections=[DraftSection(
            section_type="introduction",
            heading="Introduction",
            body="Body with [C1].",
            claim_ids=["C1"],
        )],
        claims=[DraftClaim(
            claim_id="C1", paragraph_id="P_0001",
            source_quote="hallucinated quote", node_id=None,
        )],
    )
    (run_dir / "draft.json").write_text(draft_report.model_dump_json(), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({
            "run_id": "bad-draft/mock-run",
            "query": "Blocked Draft",
            "mock": True,
            "status": "blocked_by_draft_audit",
            "draft_passed": False,
        }),
        encoding="utf-8",
    )

    runs_base = tmp_path / "output-runs"
    router = OmniSupervisorRouter(use_mock=True, runs_base=str(runs_base))
    await router.route(RouterRequest(
        query=str(run_dir),
        lens="general",
        target_module=ModuleType.REVIEW,
        use_mock=True,
    ))

    manifests = list(runs_base.rglob("manifest.json"))
    assert len(manifests) == 1
    run_out = manifests[0].parent
    out_manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert out_manifest["status"] == "blocked_by_source_audit"
    assert out_manifest["review_passed"] is False
    assert out_manifest["source_run_id"] == "bad-draft/mock-run"
    assert out_manifest["source_draft_passed"] is False
    failure = json.loads((run_out / "failure.json").read_text(encoding="utf-8"))
    assert failure["stage"] == "source_provenance"
    assert failure["source_status"] == "blocked_by_draft_audit"
    assert not (run_out / "review.json").exists()
    assert not (run_out / "review.md").exists()


class RecordingMockProvider(MockProvider):
    """프롬프트 격리(독립성) 검증용 — 호출된 (schema, prompt)를 기록."""

    def __init__(self):
        self.prompts = []

    def generate_structured_output(self, prompt, schema):
        self.prompts.append((schema.__name__, prompt))
        return super().generate_structured_output(prompt, schema)


class CorrectingIndependentProvider(MockProvider):
    """첫 PanelistReview 호출만 환각 인용 → 패널 단위 재시도 격리 검증."""

    def __init__(self):
        self.panelist_calls = 0

    def generate_structured_output(self, prompt, schema):
        if schema.__name__ == "PanelistReview":
            self.panelist_calls += 1
            if self.panelist_calls == 1:
                import re
                name = re.search(r"^Panelist Name:\s*(.+)$", prompt, re.M).group(1).strip()
                return schema.model_validate({
                    "panelist": name, "score": 40,
                    "feedback": "Hallucinated critique.",
                    "source_quotes": ["this quote does not exist in the draft"],
                })
        return super().generate_structured_output(prompt, schema)


class AlwaysBadIndependentProvider(MockProvider):
    def generate_structured_output(self, prompt, schema):
        if schema.__name__ == "PanelistReview":
            import re
            name = re.search(r"^Panelist Name:\s*(.+)$", prompt, re.M).group(1).strip()
            return schema.model_validate({
                "panelist": name, "score": 40,
                "feedback": "Hallucinated critique.",
                "source_quotes": ["this quote does not exist in the draft"],
            })
        return super().generate_structured_output(prompt, schema)


def test_build_review_independent_isolates_panelists(sample_draft):
    panel = PeerReviewPanel()
    provider = RecordingMockProvider()
    report = panel.build_review_independent(sample_draft, "theology", provider)

    assert {r.panelist for r in report.reviews} == {
        "Ella", "Miranda", "Methodologist", "Devil's Advocate",
    }
    assert report.editor_decision == "Accept"
    # 4 패널 + Editor 종합 = 5 호출, last_attempts는 총 호출 수
    assert len(provider.prompts) == 5
    assert panel.last_attempts == 5

    panelist_prompts = [p for s, p in provider.prompts if s == "PanelistReview"]
    editor_prompts = [p for s, p in provider.prompts if s == "EditorSynthesis"]
    assert len(panelist_prompts) == 4 and len(editor_prompts) == 1
    # 격리: 각 패널 프롬프트는 자신의 이름만 포함한다(타 패널 지침 비공개)
    all_names = {"Ella", "Miranda", "Methodologist", "Devil's Advocate"}
    for prompt in panelist_prompts:
        present = {n for n in all_names if n in prompt}
        assert len(present) == 1, f"panel prompt leaked other panelists: {present}"
    # Editor는 4인 리뷰 전부를 본다
    assert all(n in editor_prompts[0] for n in all_names)


def test_build_review_independent_retries_per_panelist(sample_draft):
    panel = PeerReviewPanel()
    provider = CorrectingIndependentProvider()
    report = panel.build_review_independent(sample_draft, "theology", provider)
    assert len(report.reviews) == 4
    assert panel.last_attempts == 6  # 5 + 첫 패널 재시도 1회


def test_build_review_independent_hard_fails_per_panelist(sample_draft):
    panel = PeerReviewPanel()
    with pytest.raises(ValueError, match="Independent review grounding failed for panelist 'Ella'"):
        panel.build_review_independent(sample_draft, "theology", AlwaysBadIndependentProvider())


@pytest.mark.anyio
async def test_router_review_independent_mode_mock(tmp_path):
    run_dir = tmp_path / "runs" / "indep" / "mock-run"
    run_dir.mkdir(parents=True)
    draft_report = DraftReport(
        title="Independent Panel Test",
        thesis="Mock thesis for independent review.",
        sections=[DraftSection(
            section_type="introduction", heading="Introduction",
            body="Body cites [C1].", claim_ids=["C1"],
        )],
        claims=[DraftClaim(
            claim_id="C1", paragraph_id="P_0001",
            source_quote="Mock thesis for independent review.", node_id=None,
        )],
    )
    (run_dir / "draft.json").write_text(draft_report.model_dump_json(), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({
            "run_id": "indep/mock-run", "query": "Independent Panel Test",
            "mock": True, "draft_passed": True,
        }),
        encoding="utf-8",
    )

    runs_base = tmp_path / "output-runs"
    router = OmniSupervisorRouter(use_mock=True, runs_base=str(runs_base))
    await router.route(RouterRequest(
        query=str(run_dir), lens="general",
        target_module=ModuleType.REVIEW, use_mock=True,
        independent_panel=True,
    ))

    manifests = list(runs_base.rglob("manifest.json"))
    assert len(manifests) == 1
    run_out = manifests[0].parent
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["review_mode"] == "independent"
    assert manifest["review_passed"] is True
    assert manifest["llm_usage"]["review_attempts"] == 5
    assert len(manifest["llm_usage"]["review_calls"]) == 5
    review = json.loads((run_out / "review.json").read_text(encoding="utf-8"))
    assert len(review["reviews"]) == 4


@pytest.mark.anyio
async def test_router_review_direct_file_is_marked_unverified(tmp_path, sample_draft):
    """manifest 없는 단독 draft.json 입력은 출처 미검증으로 명시 기록된다."""
    draft_path = tmp_path / "standalone_draft.json"
    draft_path.write_text(sample_draft.model_dump_json(), encoding="utf-8")

    runs_base = tmp_path / "output-runs"
    router = OmniSupervisorRouter(use_mock=True, runs_base=str(runs_base))
    await router.route(RouterRequest(
        query=str(draft_path),
        lens="general",
        target_module=ModuleType.REVIEW,
        use_mock=True,
    ))

    manifests = list(runs_base.rglob("manifest.json"))
    assert len(manifests) == 1
    out_manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert out_manifest["status"] == "completed"
    assert out_manifest["source_provenance"] == "unverified"
    assert "source_draft_passed" not in out_manifest
