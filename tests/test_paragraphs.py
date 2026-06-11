from omni_academic.audit.gate import AuditGate
from omni_academic.ontology.extractor import OntologyMap
from omni_academic.text.paragraphs import MAX_PARAGRAPH_TOKENS, assign_paragraph_ids


def test_assigns_sequential_ids_and_manifest():
    annotated, manifest = assign_paragraph_ids("first block\n\nsecond block")
    assert manifest == {"P_0001": "first block", "P_0002": "second block"}
    assert "[P_0001] first block" in annotated
    assert "[P_0002] second block" in annotated


def test_blank_input_yields_empty_manifest():
    annotated, manifest = assign_paragraph_ids("   \n\n  ")
    assert annotated == ""
    assert manifest == {}


def test_long_block_is_subdivided_at_sentence_boundaries():
    # 빈 줄 없는 PDF류 거대 블록: 문장 80개 × 10토큰 = 800토큰 > 350
    sentence = "This sentence has exactly nine words plus trailing index"
    block = " ".join(f"{sentence} {i:02d}." for i in range(80))
    annotated, manifest = assign_paragraph_ids(block)

    assert len(manifest) > 1
    # 연번 ID 유지 (파생 접미사 없음)
    assert list(manifest.keys()) == [f"P_{i:04d}" for i in range(1, len(manifest) + 1)]
    # 어떤 문단도 한도를 넘지 않는다
    assert all(len(t.split()) <= MAX_PARAGRAPH_TOKENS for t in manifest.values())
    # 문장 경계 분할 → 각 청크는 마침표로 끝난다(검증력 보존)
    assert all(t.endswith(".") for t in manifest.values())
    # 내용 무손실: 토큰 시퀀스가 동일하다
    assert " ".join(manifest.values()).split() == block.split()


def test_short_blocks_are_untouched():
    doc = "Alpha one two.\n\nBeta three four."
    _, manifest = assign_paragraph_ids(doc)
    assert manifest == {"P_0001": "Alpha one two.", "P_0002": "Beta three four."}


def test_single_oversized_sentence_is_hard_split():
    block = ("word " * 800).strip()  # 마침표 없는 800토큰 단일 문장
    _, manifest = assign_paragraph_ids(block)
    assert len(manifest) >= 3
    assert all(len(t.split()) <= MAX_PARAGRAPH_TOKENS for t in manifest.values())


def test_audit_gate_warns_on_coarse_external_manifest():
    """직접 주입된(분할기를 거치지 않은) 거대 문단 manifest는 경고된다."""
    coarse_manifest = {"P_0001": "tok " * (MAX_PARAGRAPH_TOKENS + 50)}
    report = AuditGate().verify_ontology(
        OntologyMap(nodes=[], edges=[]), paragraph_manifest=coarse_manifest,
    )
    assert any(f.code == "COARSE_PARAGRAPH" for f in report.findings)
    assert report.passed  # warning이므로 차단하지 않음


def test_audit_gate_no_coarse_warning_for_split_output():
    block = "Sentence with several words here. " * 200
    _, manifest = assign_paragraph_ids(block)
    report = AuditGate().verify_ontology(
        OntologyMap(nodes=[], edges=[]), paragraph_manifest=manifest,
    )
    assert not any(f.code == "COARSE_PARAGRAPH" for f in report.findings)
