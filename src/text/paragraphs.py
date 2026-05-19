import re
from typing import Set, Tuple


def assign_paragraph_ids(markdown: str) -> Tuple[str, Set[str]]:
    """원문을 빈 줄 기준으로 문단 분할하고 `P_0001` 형태의 ID를 부여한다.

    반환: (ID가 주입된 주석본, manifest 집합).
    AuditGate는 이 manifest로 노드의 paragraph_id 실존 여부를 대조하여
    원문에 근거 없는(=환각) 노드를 차단한다.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", markdown or "") if b.strip()]
    manifest: Set[str] = set()
    annotated = []
    for i, block in enumerate(blocks, 1):
        pid = f"P_{i:04d}"
        manifest.add(pid)
        annotated.append(f"[{pid}] {block}")
    return "\n\n".join(annotated), manifest
