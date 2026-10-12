from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


class Config(dict):
    """config.yaml을 점(.) 경로로 꺼내 쓰는 얇은 래퍼. 예: cfg.get_path("video.fps")"""

    def get_path(self, dotted: str, default: Any = None) -> Any:
        node: Any = self
        for key in dotted.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def resolve(self, dotted: str) -> Path:
        """설정에 적힌 상대경로를 저장소 루트 기준 절대경로로 바꾼다."""
        p = Path(self.get_path(dotted))
        return p if p.is_absolute() else ROOT / p


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, encoding="utf-8") as f:
        return Config(yaml.safe_load(f))
