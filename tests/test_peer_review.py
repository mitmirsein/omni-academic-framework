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
        "mock": True
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
        json.dumps({"run_id": "test-query/mock-run", "query": "CS Scale Test"}),
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
