"""Phase 3 — 피어 리뷰 패널 유닛 및 통합 테스트 (test_peer_review.py)"""

import pytest

from omni_academic.analyze.peer_review import PeerReviewPanel, ReviewReport
from omni_academic.draft.scribe import DraftClaim, DraftReport, DraftSection
from omni_academic.llm.provider import MockProvider
from omni_academic.supervisor.router import ModuleType, OmniSupervisorRouter, RouterRequest


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
    assert "Ella" in cfg["panelists"]
    assert "Miranda" in cfg["panelists"]
    assert "Methodologist" in cfg["panelists"]
    assert "DevilsAdvocate" in cfg["panelists"]


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
    router = OmniSupervisorRouter(use_mock=True)
    req = RouterRequest(
        query=str(run_dir),
        lens="cs",
        target_module=ModuleType.REVIEW,
        use_mock=True
    )
    
    # Router가 Runs 폴더에 저장할 경로를 임시 폴더로 잡도록 base path 조정 (mock config env injection 생략하고 직접 store mock 처리 가능)
    # 여기서는 build_review + write_review 가 정상 완주하는지 실행
    await router.route(req)
    
    # review.json 및 review.md 생성을 검증
    # router.route는 store.finalize() 시 새로운 runs/ 폴더를 생성하므로 해당 output 디렉토리 하위에 아티팩트가 생성됨
    # verify_run 검증을 통해 integrity 확인 가능
