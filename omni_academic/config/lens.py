import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_LENS = "general"

# 패키지에 동봉된 기본 렌즈(설치 시 wheel force-include로 함께 배포된다).
_PACKAGED_LENSES = Path(__file__).resolve().parent.parent / "lenses"


class LensNotFoundError(FileNotFoundError):
    pass


class LensConfigError(ValueError):
    """렌즈 YAML이 알려진 필드의 타입 계약을 위반함 — 조용한 무시 대신 명시 실패."""


class LensConfig(BaseModel):
    """렌즈 어댑터의 알려진 필드 계약 (헌법 §2 — 도메인 규칙 주입 통로).

    어댑터 주입이 핵심 메커니즘이므로 주입 실패(오타 필드, 타입 위반)는
    조용히 빈 지시로 동작하지 않고 시끄럽게 알린다. 미지 키는 허용하되
    `lens_warnings()`로 표면화한다(전방 호환).
    """

    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    description: Optional[str] = None
    focus_areas: List[str] = Field(default_factory=list)
    analysis_prompt: str = ""
    ontology_directive: str = ""
    recon_clients: List[str] = Field(default_factory=list)
    coverage_thresholds: Dict[str, Any] = Field(default_factory=dict)


def lens_warnings(lens_cfg: Dict[str, Any]) -> List[str]:
    """알려진 렌즈 필드가 아닌 top-level 키를 경고 문자열로 반환한다."""
    known = set(LensConfig.model_fields)
    unknown = sorted(k for k in (lens_cfg or {}) if k not in known)
    if unknown:
        return ["unknown keys: " + ", ".join(unknown)]
    return []


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
    """렌즈 YAML을 로드하고 알려진 필드의 타입을 검증한다.

    없으면 LensNotFoundError, 타입 계약 위반이면 LensConfigError.
    도메인 규칙은 코드가 아니라 이 파일에서 주입된다(헌법 §2: 도메인 독립성).
    """
    path = Path(resolve_lens_dir(lens_dir)) / f"{lens_name}.yaml"
    if not path.is_file():
        raise LensNotFoundError(f"렌즈 '{lens_name}' 를 찾을 수 없습니다: {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise LensConfigError(f"렌즈 '{lens_name}' YAML 루트가 매핑이 아닙니다: {path}")
    try:
        LensConfig.model_validate(cfg)
    except ValidationError as e:
        raise LensConfigError(
            f"렌즈 '{lens_name}' 설정이 필드 계약을 위반합니다 ({path}):\n{e}"
        ) from e
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
