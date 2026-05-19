from pathlib import Path
from typing import Any, Dict, List

import yaml

DEFAULT_LENS = "general"


class LensNotFoundError(FileNotFoundError):
    pass


def load_lens(lens_name: str, lens_dir: str = "lenses") -> Dict[str, Any]:
    """렌즈 YAML을 로드한다. 없으면 LensNotFoundError.

    도메인 규칙은 코드가 아니라 이 파일에서 주입된다(헌법 §2: 도메인 독립성).
    """
    path = Path(lens_dir) / f"{lens_name}.yaml"
    if not path.is_file():
        raise LensNotFoundError(f"렌즈 '{lens_name}' 를 찾을 수 없습니다: {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg


def get_recon_client_names(lens_cfg: Dict[str, Any]) -> List[str]:
    """렌즈 설정에서 recon 클라이언트 이름 리스트를 반환한다."""
    clients = lens_cfg.get("recon_clients") or []
    return [str(c).strip().lower() for c in clients if str(c).strip()]
