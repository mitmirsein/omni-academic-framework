from src.audit.gate import AuditGate
from src.ontology.extractor import (
    Edge,
    EntityClass,
    Node,
    OntologyMap,
    RelationPredicate,
)


def _map(pid_a="P_0001", pid_b="P_0002", quote_a="Alpha claim", quote_b="Beta method"):
    return OntologyMap(
        nodes=[
            Node(
                id="n1", label="A", entity_class=EntityClass.CONCEPT,
                paragraph_id=pid_a, source_quote=quote_a,
            ),
            Node(
                id="n2", label="B", entity_class=EntityClass.METHOD,
                paragraph_id=pid_b, source_quote=quote_b,
            ),
        ],
        edges=[
            Edge(source_id="n1", target_id="n2",
                 predicate=RelationPredicate.USES_METHOD,
                 reasoning="A applies method B per section 2.",
                 source_quote=quote_a),
        ],
    )


def test_grounded_ontology_passes():
    report = AuditGate().verify_ontology(
        _map(),
        paragraph_manifest={
            "P_0001": "Alpha claim appears here.",
            "P_0002": "Beta method appears here.",
        },
    )
    assert report.passed
    assert report.score == 100


def test_ungrounded_node_fails_as_hallucination():
    # mock provider가 내놓는 P_01류는 실제 manifest에 없으므로 반드시 실패해야 한다.
    report = AuditGate().verify_ontology(_map("P_01", "P_02"),
                                         paragraph_manifest={"P_0001", "P_0002"})
    assert not report.passed
    assert any(f.code == "UNGROUNDED_NODE" for f in report.findings)


def test_missing_manifest_is_low_trust_failure():
    report = AuditGate().verify_ontology(_map(), paragraph_manifest=None)
    assert not report.passed
    assert any(f.code == "NO_SOURCE_MANIFEST" for f in report.findings)


def test_self_loop_is_error():
    m = _map()
    m.edges[0].target_id = "n1"
    report = AuditGate().verify_ontology(
        m,
        paragraph_manifest={
            "P_0001": "Alpha claim appears here.",
            "P_0002": "Beta method appears here.",
        },
    )
    assert not report.passed
    assert any(f.code == "SELF_LOOP" for f in report.findings)


def test_quote_must_be_in_declared_paragraph():
    report = AuditGate().verify_ontology(
        _map(quote_a="not in paragraph"),
        paragraph_manifest={
            "P_0001": "Alpha claim appears here.",
            "P_0002": "Beta method appears here.",
        },
    )
    assert not report.passed
    assert any(f.code == "UNGROUNDED_QUOTE" for f in report.findings)


def test_legacy_manifest_set_skips_quote_check():
    report = AuditGate().verify_ontology(_map(), paragraph_manifest={"P_0001", "P_0002"})
    assert report.passed


def test_short_quote_warns_but_does_not_fail():
    report = AuditGate().verify_ontology(
        _map(quote_a="Alpha"),
        paragraph_manifest={
            "P_0001": "Alpha appears here.",
            "P_0002": "Beta method appears here.",
        },
    )
    assert report.passed
    assert any(f.code == "QUOTE_TOO_SHORT" for f in report.findings)


def test_duplicate_node_quotes_warn():
    report = AuditGate().verify_ontology(
        _map(quote_a="Shared quote", quote_b="Shared quote"),
        paragraph_manifest={
            "P_0001": "Shared quote appears here.",
            "P_0002": "Shared quote appears here too.",
        },
    )
    assert report.passed
    assert any(f.code == "DUPLICATE_NODE_QUOTE" for f in report.findings)


def test_edge_quote_must_attach_to_endpoint_paragraphs():
    m = _map(quote_a="Alpha claim", quote_b="Beta method")
    m.edges[0].source_quote = "Gamma context"

    report = AuditGate().verify_ontology(
        m,
        paragraph_manifest={
            "P_0001": "Alpha claim appears here.",
            "P_0002": "Beta method appears here.",
            "P_0003": "Gamma context appears elsewhere.",
        },
    )
    assert report.passed
    assert any(f.code == "DETACHED_EDGE_QUOTE" for f in report.findings)
