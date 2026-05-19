import os
import shutil


def resolve_tool(env_name: str, path_default: str = "") -> str:
    """외부 툴 경로 통일 규약.

    우선순위: 명시적 env(`OMNI_*`) > PATH 탐색(`path_default` 이름) > "".
    머신-로컬 절대경로 하드코딩을 금지한다(이식성·헌법). 미해결 시 ""를
    반환하고, 호출부는 가짜 결과 대신 정직하게 실패해야 한다.

    예) resolve_tool("OMNI_LIGHTPANDA_BIN", "lightpanda")
    """
    explicit = os.environ.get(env_name, "").strip()
    if explicit:
        return explicit
    if path_default:
        found = shutil.which(path_default)
        if found:
            return found
    return ""
