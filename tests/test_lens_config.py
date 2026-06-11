"""렌즈 YAML 스키마 검증 테스트 (QUALITY_IMPROVEMENT_PLAN.md F9).

어댑터 주입(헌법 §2)이 핵심 메커니즘이므로, 주입 실패(타입 위반·오타 키)는
조용히 빈 지시로 동작하지 말고 시끄럽게 드러나야 한다.
"""

from pathlib import Path

import pytest

from omni_academic.config.lens import (
    LensConfigError,
    lens_warnings,
    load_lens,
)
from omni_academic.supervisor.router import _list_lenses

BUNDLED = Path("lenses")


def _write_lens(tmp_path, name: str, body: str) -> str:
    (tmp_path / f"{name}.yaml").write_text(body, encoding="utf-8")
    return str(tmp_path)


def test_valid_lens_loads_without_warnings(tmp_path):
    lens_dir = _write_lens(tmp_path, "valid", (
        'name: "Valid Lens"\n'
        "focus_areas:\n  - Area One\n"
        'analysis_prompt: "Analyze."\n'
        "recon_clients:\n  - arxiv\n"
        "coverage_thresholds:\n  min_paragraph_coverage: 0.4\n"
    ))
    cfg = load_lens("valid", lens_dir)
    assert cfg["name"] == "Valid Lens"
    assert lens_warnings(cfg) == []


def test_type_violation_fails_loudly(tmp_path):
    # focus_areas가 list가 아닌 문자열 → 조용한 무시 대신 명시 실패
    lens_dir = _write_lens(tmp_path, "broken", (
        'name: "Broken"\nfocus_areas: "not a list"\n'
    ))
    with pytest.raises(LensConfigError, match="broken"):
        load_lens("broken", lens_dir)


def test_non_mapping_root_fails_loudly(tmp_path):
    lens_dir = _write_lens(tmp_path, "listroot", "- just\n- a list\n")
    with pytest.raises(LensConfigError):
        load_lens("listroot", lens_dir)


def test_unknown_keys_are_warned_not_rejected(tmp_path):
    lens_dir = _write_lens(tmp_path, "typo", (
        'name: "Typo Lens"\nfocus_area: ["singular typo"]\n'
    ))
    cfg = load_lens("typo", lens_dir)  # 전방 호환: 거부하지 않음
    warnings = lens_warnings(cfg)
    assert warnings and "focus_area" in warnings[0]


def test_all_bundled_lenses_satisfy_contract():
    for path in sorted(BUNDLED.glob("*.yaml")):
        cfg = load_lens(path.stem, str(BUNDLED))  # LensConfigError 없이 로드
        if path.stem == "review_panel":
            # 리뷰 패널 설정은 렌즈가 아님 — 미지 키 경고로 표면화된다.
            assert lens_warnings(cfg)
        else:
            assert lens_warnings(cfg) == [], f"{path.stem}: {lens_warnings(cfg)}"


def test_list_lenses_reports_validation_issues(tmp_path):
    _write_lens(tmp_path, "good", 'name: "Good"\n')
    _write_lens(tmp_path, "bad", "focus_areas: 17\n")
    _write_lens(tmp_path, "odd", 'name: "Odd"\nmystery_key: 1\n')

    rows = {r["id"]: r for r in _list_lenses(str(tmp_path))}
    assert rows["good"]["issues"] == []
    assert rows["bad"]["name"] == "(invalid)"
    assert rows["bad"]["issues"]
    assert any("mystery_key" in i for i in rows["odd"]["issues"])
