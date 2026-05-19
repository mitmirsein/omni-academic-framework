from src.text.paragraphs import assign_paragraph_ids


def test_assigns_sequential_ids_and_manifest():
    annotated, manifest = assign_paragraph_ids("first block\n\nsecond block")
    assert manifest == {"P_0001": "first block", "P_0002": "second block"}
    assert "[P_0001] first block" in annotated
    assert "[P_0002] second block" in annotated


def test_blank_input_yields_empty_manifest():
    annotated, manifest = assign_paragraph_ids("   \n\n  ")
    assert annotated == ""
    assert manifest == {}
