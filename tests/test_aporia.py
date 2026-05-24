"""아포리아(환원불가 역설) 보존 — 헌법 §3.

신학 등에서 양극이 동시에 참으로 긍정되는 역설(vere Deus/vere homo)이
평탄화되지 않도록, `in_tension_with` 술어가 1급으로 감사를 통과하고
도메인 지시가 추출 프롬프트에 주입되는지 검증한다. 도메인 용어는 코어가
아니라 lenses/theology.yaml(어댑터)에 있어야 한다(§2).
"""

from omni_academic.audit.gate import AuditGate
from omni_academic.config.lens import get_ontology_directive, load_lens
from omni_academic.ontology.extractor import (
    Edge,
    EntityClass,
    Node,
    OntologyExtractor,
    OntologyMap,
    RelationPredicate,
)


def test_in_tension_with_predicate_exists_and_is_distinct():
    assert RelationPredicate.IN_TENSION_WITH.value == "in_tension_with"
    # CONFLICTS_WITH와 별개 술어여야 한다(역설 != 경합)
    assert RelationPredicate.IN_TENSION_WITH != RelationPredicate.CONFLICTS_WITH


def test_aporia_edge_passes_audit_unflattened():
    """양극을 보존한 in_tension_with 엣지는 감사에서 살아남아야 한다(에러 0)."""
    para = (
        "The council confessed Christ as vere Deus et vere homo: truly God and "
        "truly man, two natures in one person without confusion."
    )
    manifest = {"P_0001": para}
    quote_god = "vere Deus"
    quote_man = "vere homo"
    ontology = OntologyMap(
        nodes=[
            Node(id="n1", label="vere Deus", entity_class=EntityClass.CLAIM,
                 paragraph_id="P_0001", source_quote=quote_god),
            Node(id="n2", label="vere homo", entity_class=EntityClass.CLAIM,
                 paragraph_id="P_0001", source_quote=quote_man),
        ],
        edges=[
            Edge(source_id="n1", target_id="n2",
                 predicate=RelationPredicate.IN_TENSION_WITH,
                 reasoning="Both natures are affirmed of one person — irreducible paradox.",
                 source_quote="two natures in one person without confusion"),
        ],
    )
    report = AuditGate().verify_ontology(ontology, paragraph_manifest=manifest)
    assert report.passed, [f.code for f in report.findings if f.severity == "error"]
    # 양극이 모두 보존됐는지(평탄화되어 하나로 합쳐지지 않음)
    assert {n.label for n in ontology.nodes} == {"vere Deus", "vere homo"}


def test_theology_lens_carries_aporia_directive_not_core():
    directive = get_ontology_directive(load_lens("theology"))
    assert directive, "theology 렌즈에 ontology_directive가 있어야 한다"
    low = directive.lower()
    assert "in_tension_with" in low
    assert "vere deus" in low and "vere homo" in low
    # general 렌즈엔 도메인 지시가 없어야 한다(도메인 중립 §2)
    assert get_ontology_directive(load_lens("general")) == ""


def test_extract_injects_directive_into_prompt():
    captured = {}

    class _SpyProvider:
        last_usage = None

        def generate_structured_output(self, prompt, schema):
            captured["prompt"] = prompt
            return OntologyMap(nodes=[], edges=[])

    OntologyExtractor(llm_provider=_SpyProvider()).extract(
        "[P_0001] some source text", directive="PRESERVE_APORIA_MARKER"
    )
    assert "PRESERVE_APORIA_MARKER" in captured["prompt"]
    # directive 없으면 주입 흔적도 없어야 한다(도메인 중립 기본)
    captured.clear()
    OntologyExtractor(llm_provider=_SpyProvider()).extract("[P_0001] text")
    assert "Domain extraction directive" not in captured["prompt"]
