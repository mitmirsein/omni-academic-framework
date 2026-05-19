import re
from typing import Dict, Tuple


def assign_paragraph_ids(markdown: str) -> Tuple[str, Dict[str, str]]:
    """원문을 빈 줄 기준으로 문단 분할하고 `P_0001` 형태의 ID를 부여한다.

    반환: (ID가 주입된 주석본, paragraph_map[{pid: 문단 텍스트}]).
    AuditGate는 이 map으로 (1) 노드 paragraph_id 실존, (2) source_quote가
    해당 문단 텍스트에 실제 포함되는지를 대조해 환각을 기계적으로 차단한다.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", markdown or "") if b.strip()]
    paragraph_map: Dict[str, str] = {}
    annotated = []
    for i, block in enumerate(blocks, 1):
        pid = f"P_{i:04d}"
        paragraph_map[pid] = block
        annotated.append(f"[{pid}] {block}")
    return "\n\n".join(annotated), paragraph_map
