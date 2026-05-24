import os
from pathlib import Path
from typing import Any, Dict, List

import yaml

DEFAULT_LENS = "general"

# 패키지에 동봉된 기본 렌즈(설치 시 wheel force-include로 함께 배포된다).
_PACKAGED_LENSES = Path(__file__).resolve().parent.parent / "lenses"


class LensNotFoundError(FileNotFoundError):
    pass


def resolve_lens_dir(lens_dir: str | None = "lenses") -> str:
    """렌즈 디렉터리를 해석한다 (설치 후 임의 CWD에서도 동작하도록).

    우선순위: 명시 인자 > `$OMNI_LENS_DIR` > `./lenses`(CWD) > 패키지 동봉본.
    어느 후보도 실존하지 않으면 원래 값(또는 'lenses')을 그대로 반환해,
    호출부가 LensNotFoundError로 정직하게 실패하게 한다(경로 추측 금지).
    """
    candidates: List[Path] = []
    if lens_dir:
        candidates.append(Path(lens_dir))
    env = os.environ.get("OMNI_LENS_DIR", "").strip()
    if env:
        candidates.append(Path(env))
    candidates.append(Path("lenses"))
    candidates.append(_PACKAGED_LENSES)
    for c in candidates:
        if c.is_dir():
            return str(c)
    return lens_dir or "lenses"


def load_lens(lens_name: str, lens_dir: str = "lenses") -> Dict[str, Any]:
    """렌즈 YAML을 로드한다. 없으면 LensNotFoundError.

    도메인 규칙은 코드가 아니라 이 파일에서 주입된다(헌법 §2: 도메인 독립성).
    """
    path = Path(resolve_lens_dir(lens_dir)) / f"{lens_name}.yaml"
    if not path.is_file():
        raise LensNotFoundError(f"렌즈 '{lens_name}' 를 찾을 수 없습니다: {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg


def get_recon_client_names(lens_cfg: Dict[str, Any]) -> List[str]:
    """렌즈 설정에서 recon 클라이언트 이름 리스트를 반환한다."""
    clients = lens_cfg.get("recon_clients") or []
    return [str(c).strip().lower() for c in clients if str(c).strip()]


def get_ontology_directive(lens_cfg: Dict[str, Any]) -> str:
    """렌즈가 온톨로지 추출에 주입할 도메인 지시(없으면 빈 문자열).

    코어 추출기는 도메인 용어를 모르고(헌법 §2), 분야별 강조(예: 신학의
    아포리아 보존)는 이 어댑터 필드로만 주입된다.
    """
    return str(lens_cfg.get("ontology_directive") or "").strip()
