from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel


class BaseLLMProvider(ABC):
    """
    모든 LLM 플러그인의 추상 기본 클래스입니다.
    어떤 모델(OpenAI, Anthropic, Gemini 등)을 사용하든 동일한 인터페이스로 Pydantic 스키마를 반환해야 합니다.
    """

    #: 직전 호출의 model/usage 메타데이터 (운용 감사용). 호출 후 갱신된다.
    last_usage: "Optional[dict]" = None

    @abstractmethod
    def generate_structured_output(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        pass

class MockProvider(BaseLLMProvider):
    """
    안티그래비티 IDE 환경 등 API 키 없이 즉시 가동(엔진 테스트)하기 위한 Mock 플러그인입니다.
    """
    def generate_structured_output(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        # manifest-aware mock: 프롬프트의 실제 [P_XXXX] 문단을 파싱해
        # 존재하는 paragraph_id와 verbatim source_quote만 사용한다.
        # → AuditGate(grounding + quote-in-paragraph)를 정상 통과해야
        #   README의 clone-즉시 --mock 경로가 깨지지 않는다.
        import re

        # 운용 감사: mock임을 명시 낙인(실 usage가 아님을 위장 금지).
        self.last_usage = {"model": "mock", "mock": True, "schema": schema.__name__}

        if schema.__name__ == "LensAnalysisReport":
            import ast

            blocks = re.findall(r"\[(P_\d+)\]\s*(.+?)(?=\n\[P_\d+\]|\Z)", prompt, re.S)
            lens_match = re.search(r"^Lens ID:\s*(.+)$", prompt, re.M)
            lens = lens_match.group(1).strip() if lens_match else "mock"
            focus_match = re.search(r"^Focus Areas:\s*(.+)$", prompt, re.M)
            try:
                focus_areas = ast.literal_eval(focus_match.group(1)) if focus_match else []
            except (SyntaxError, ValueError):
                focus_areas = []
            findings = []
            for i, (pid, text) in enumerate(blocks[:3], 1):
                quote = text.strip()[:80]
                findings.append({
                    "focus_area": (
                        str(focus_areas[i - 1])
                        if i - 1 < len(focus_areas)
                        else f"Mock Focus {i}"
                    ),
                    "paragraph_id": pid,
                    "source_quote": quote,
                    "analysis": "Mock source-bound analysis for pipeline verification.",
                })
            return schema.model_validate({
                "lens": lens,
                "executive_summary": (
                    "Mock LLM analysis generated from real paragraph anchors."
                ),
                "findings": findings,
                "limitations": ["MockProvider output is not interpretive analysis."],
            })

        if schema.__name__ == "LensCriticReport":
            return schema.model_validate({
                "passed": True,
                "risk_level": "low",
                "summary": (
                    "Mock critic found no blocking issue. This validates the "
                    "critic artifact path, not real analytical quality."
                ),
                "critiques": [],
            })

        if schema.__name__ == "DraftReport":
            blocks = re.findall(r"\[(P_\d+)\]\s*(.+?)(?=\n\[P_\d+\]|\Z)", prompt, re.S)
            if not blocks:
                return schema.model_validate({
                    "title": "Mock Draft (no source paragraphs found)",
                    "thesis": "MockProvider found no [P_XXXX] anchors to ground a draft.",
                    "sections": [],
                    "claims": [],
                    "open_tensions": [
                        "MockProvider draft is a pipeline check, not real synthesis."
                    ],
                })
            claims = [
                {
                    "claim_id": f"C{i}",
                    "paragraph_id": pid,
                    "source_quote": text.strip()[:80],
                    "node_id": None,
                }
                for i, (pid, text) in enumerate(blocks[:3], 1)
            ]
            anchors = " ".join(f"[{c['claim_id']}]" for c in claims)
            sections = [
                {
                    "section_type": "introduction",
                    "heading": "Introduction",
                    "body": f"Mock introduction grounded in source anchors {anchors}.",
                    "claim_ids": [c["claim_id"] for c in claims],
                },
                {
                    "section_type": "conclusion",
                    "heading": "Conclusion",
                    "body": f"Mock conclusion restating the grounded claims {anchors}.",
                    "claim_ids": [c["claim_id"] for c in claims],
                },
            ]
            return schema.model_validate({
                "title": "Mock Source-Bound Draft",
                "thesis": "Mock thesis derived only from real paragraph anchors.",
                "sections": sections,
                "claims": claims,
                "open_tensions": [
                    "MockProvider draft is a pipeline check, not real synthesis."
                ],
            })

        from omni_academic.ontology.extractor import (
            Edge,
            EntityClass,
            Node,
            OntologyMap,
            RelationPredicate,
        )

        blocks = re.findall(r"\[(P_\d+)\]\s*(.+?)(?=\n\[P_\d+\]|\Z)", prompt, re.S)
        if not blocks:
            # 문단을 못 찾으면 정직하게 빈 그래프(감사에서 NO 노드 → 통과는
            # 하되 내용 0 — 가짜 P_01 환각보다 정직하다).
            return OntologyMap(nodes=[], edges=[])

        nodes, edges = [], []
        for i, (pid, text) in enumerate(blocks[:3], 1):
            quote = " ".join(text.split())[:60]
            nodes.append(Node(
                id=f"n{i}", label=f"Mock Concept {i}",
                entity_class=EntityClass.CONCEPT,
                paragraph_id=pid, source_quote=quote,
            ))
        for i in range(len(nodes) - 1):
            edges.append(Edge(
                source_id=nodes[i].id, target_id=nodes[i + 1].id,
                predicate=RelationPredicate.BUILDS_ON,
                reasoning="Auto-generated mock relation for pipeline test.",
                source_quote=nodes[i].source_quote,
            ))
        return OntologyMap(nodes=nodes, edges=edges)

class OpenAIProvider(BaseLLMProvider):
    """OpenAI API 플러그인 (gpt-4o)"""
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def generate_structured_output(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        # TODO: openai.beta.chat.completions.parse() 구현
        raise NotImplementedError("OpenAI API 연결은 향후 플러그인에서 활성화됩니다.")

class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude 플러그인.

    강제 tool-use(`tool_choice`)로 Pydantic 스키마를 그대로 반환받고,
    안정적인 하네스 지침(system)에 prompt caching을 건다. 도메인 규칙은
    여기에 하드코딩하지 않는다(헌법 §2) — 입력 문서에서 동적으로 파악한다.
    """

    DEFAULT_MODEL = "claude-opus-4-7"

    SYSTEM_INSTRUCTION = (
        "You are a domain-agnostic academic ontology extractor. "
        "Decompose the supplied scholarly text into a knowledge graph of "
        "universal entity classes and standard relation predicates ONLY. "
        "Hard rules:\n"
        "1. Every node's paragraph_id MUST be copied verbatim from a [P_XXXX] "
        "marker that actually appears in the supplied text. Never invent a "
        "paragraph_id. If a claim has no [P_XXXX] anchor, do not emit a node "
        "for it.\n"
        "2. Do not flatten, summarize, or resolve logical tensions/aporia in "
        "the source. Preserve contradictory poles as separate nodes/edges. When "
        "two affirmations are BOTH held as true and form an irreducible paradox "
        "(not a competing claim where one defeats the other), keep both poles as "
        "separate nodes and connect them with the `in_tension_with` predicate — "
        "never collapse them into one node or resolve the paradox. Use "
        "`conflicts_with` only for genuinely competing/incompatible positions.\n"
        "3. Do not inject domain-specific terminology or citation rules of "
        "your own; reflect only what the text states.\n"
        "4. Every edge.reasoning must quote or tightly paraphrase the "
        "supporting span from the source.\n"
        "5. Every node AND every edge MUST include a `source_quote`: a "
        "string copied VERBATIM (exact substring, <=200 chars) from the "
        "text of its cited [P_XXXX] paragraph. The mechanical auditor "
        "rejects any quote not literally present in that paragraph — do "
        "not paraphrase, normalize, or translate the source_quote.\n"
        "Return the result solely by calling the provided tool."
    )

    LENS_ANALYSIS_SYSTEM_INSTRUCTION = (
        "You are a domain-agnostic academic lens analyst. "
        "Analyze only the supplied text and lens instructions. Hard rules:\n"
        "1. Every finding must cite a paragraph_id copied verbatim from a "
        "[P_XXXX] marker in the supplied text.\n"
        "2. Every finding.source_quote must be copied verbatim from that "
        "paragraph. Do not paraphrase source_quote.\n"
        "3. Do not add claims, contexts, citations, or domain terminology not "
        "grounded in the supplied text.\n"
        "4. Preserve unresolved tensions and limitations.\n"
        "Return the result solely by calling the provided tool."
    )

    DRAFT_SYSTEM_INSTRUCTION = (
        "You are a domain-agnostic academic scribe. Write a paper draft grounded "
        "ONLY in the supplied ontology map and source paragraphs. Hard rules:\n"
        "1. Prose body is allowed, but every factual claim MUST be registered in "
        "claims[] and referenced in the body with its [C#] anchor.\n"
        "2. Every claim.paragraph_id MUST be a real [P_XXXX] marker from the "
        "source, and claim.source_quote MUST be an exact verbatim substring of "
        "that paragraph (do not paraphrase, normalize, or translate).\n"
        "3. If a claim maps to an ontology node, set claim.node_id to a real node "
        "id from the supplied map.\n"
        "4. Do not introduce facts, citations, or figures absent from the source. "
        "Do not flatten contradictions — record unresolved tensions in "
        "open_tensions.\n"
        "Return the result solely by calling the provided tool."
    )

    def __init__(self, api_key: str, model: str | None = None):
        if not api_key:
            raise ValueError(
                "AnthropicProvider: ANTHROPIC_API_KEY가 비어 있습니다. "
                "오프라인 실행은 router의 --mock 플래그를 사용하세요."
            )
        try:
            import anthropic
        except ModuleNotFoundError as e:
            raise ValueError(
                "AnthropicProvider: 'anthropic' 패키지가 필요합니다 "
                "(`uv run --extra llm ...` 또는 `uv sync --extra llm`). 또는 --mock 사용."
            ) from e
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model or self.DEFAULT_MODEL
        # 토큰 예산: 운용 환경에서 OMNI_LLM_MAX_TOKENS로 상한 조정 가능.
        import os

        try:
            self.max_tokens = max(1024, int(os.environ.get("OMNI_LLM_MAX_TOKENS", "16000")))
        except ValueError:
            self.max_tokens = 16000

    def generate_structured_output(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        tool_name = "emit_structured_output"
        system_instruction = {
            "OntologyMap": self.SYSTEM_INSTRUCTION,
            "DraftReport": self.DRAFT_SYSTEM_INSTRUCTION,
        }.get(schema.__name__, self.LENS_ANALYSIS_SYSTEM_INSTRUCTION)
        tool = {
            "name": tool_name,
            "description": (
                "Return structured academic output strictly conforming to the "
                "input schema. This is the only allowed output channel."
            ),
            "input_schema": schema.model_json_schema(),
        }
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system_instruction,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": prompt}],
            )
        except self._anthropic.APIError as e:
            raise RuntimeError(f"Anthropic API 호출 실패: {e}") from e

        # 운용 감사: 실제 model + 토큰 usage 기록(매 호출 갱신).
        usage = getattr(response, "usage", None)
        self.last_usage = {
            "model": getattr(response, "model", self.model),
            "mock": False,
            "schema": schema.__name__,
            "max_tokens_budget": self.max_tokens,
            "stop_reason": getattr(response, "stop_reason", None),
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
        }

        tool_block = next(
            (b for b in response.content if b.type == "tool_use"), None
        )
        if tool_block is None:
            raise RuntimeError(
                f"Anthropic 응답에 tool_use 블록이 없습니다 "
                f"(stop_reason={response.stop_reason})."
            )
        # 강제 스키마 검증 — 모델이 schema를 위반하면 여기서 차단된다.
        return schema.model_validate(tool_block.input)
