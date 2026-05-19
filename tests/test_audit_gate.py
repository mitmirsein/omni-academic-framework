from src.audit.gate import AuditGate
from src.ontology.extractor import (
    Edge,
    EntityClass,
    Node,
    OntologyMap,
    RelationPredicate,
)


def _map(pid_a="P_0001", pid_b="P_0002"):
    return OntologyMap(
        nodes=[
            Node(id="n1", label="A", entity_class=EntityClass.CONCEPT, paragraph_id=pid_a),
            Node(id="n2", label="B", entity_class=EntityClass.METHOD, paragraph_id=pid_b),
        ],
        edges=[
            Edge(source_id="n1", target_id="n2",
                 predicate=RelationPredicate.USES_METHOD,
                 reasoning="A applies method B per section 2."),
        ],
    )


def test_grounded_ontology_passes():
    report = AuditGate().verify_ontology(_map(), paragraph_manifest={"P_0001", "P_0002"})
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
    report = AuditGate().verify_ontology(m, paragraph_manifest={"P_0001", "P_0002"})
    assert not report.passed
    assert any(f.code == "SELF_LOOP" for f in report.findings)
