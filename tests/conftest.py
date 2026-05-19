import sys
from pathlib import Path

# `from src....` 절대임포트가 repo 루트 기준으로 해석되도록 보장.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
