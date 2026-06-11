import re
from typing import Dict, List, Tuple

# 한 문단의 최대 토큰(공백 분리) 수. PDF 추출 텍스트처럼 빈 줄이 드문 입력에서
# 페이지 단위 거대 블록이 생기면 "quote가 해당 문단에 있는가" 검사가 사실상
# "문서 전체에 있는가"로 퇴화한다 → 문장 경계에서 하위 분할해 검증력을 보존한다.
MAX_PARAGRAPH_TOKENS = 350

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?。!?])\s+")


def _token_count(text: str) -> int:
    return len(text.split())


def _split_long_block(block: str, max_tokens: int) -> List[str]:
    """max_tokens 초과 블록을 문장 경계에서 하위 분할한다.

    단일 문장이 한도를 넘으면 단어 단위로 강제 분할한다(검증력 우선).
    """
    if _token_count(block) <= max_tokens:
        return [block]

    pieces: List[str] = []
    for sentence in _SENTENCE_BOUNDARY_RE.split(block):
        if not sentence.strip():
            continue
        words = sentence.split()
        if len(words) <= max_tokens:
            pieces.append(sentence.strip())
        else:
            for i in range(0, len(words), max_tokens):
                pieces.append(" ".join(words[i:i + max_tokens]))

    chunks: List[str] = []
    current: List[str] = []
    current_tokens = 0
    for piece in pieces:
        piece_tokens = _token_count(piece)
        if current and current_tokens + piece_tokens > max_tokens:
            chunks.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(piece)
        current_tokens += piece_tokens
    if current:
        chunks.append(" ".join(current))
    return chunks or [block]


def assign_paragraph_ids(
    markdown: str,
    max_tokens: int = MAX_PARAGRAPH_TOKENS,
) -> Tuple[str, Dict[str, str]]:
    """원문을 빈 줄 기준으로 문단 분할하고 `P_0001` 형태의 ID를 부여한다.

    max_tokens를 초과하는 거대 블록은 문장 경계에서 하위 분할한 뒤 연번
    ID를 이어 부여한다(파생 접미사 없이 `P_\\d+` 계약 유지).

    반환: (ID가 주입된 주석본, paragraph_map[{pid: 문단 텍스트}]).
    AuditGate는 이 map으로 (1) 노드 paragraph_id 실존, (2) source_quote가
    해당 문단 텍스트에 실제 포함되는지를 대조해 환각을 기계적으로 차단한다.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", markdown or "") if b.strip()]
    paragraph_map: Dict[str, str] = {}
    annotated = []
    counter = 0
    for block in blocks:
        for chunk in _split_long_block(block, max(1, max_tokens)):
            counter += 1
            pid = f"P_{counter:04d}"
            paragraph_map[pid] = chunk
            annotated.append(f"[{pid}] {chunk}")
    return "\n\n".join(annotated), paragraph_map
