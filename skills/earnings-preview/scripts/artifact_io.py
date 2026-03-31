"""Generic artifact I/O helpers for skill scripts.

Reusable across skills — read/write JSON and markdown artifacts under
``data/artifacts/``.  All JSON writes include ``schema_version`` and
``updated_at`` automatically.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent
for _ in range(6):
    if (_ROOT / "data" / "artifacts").exists():
        break
    _ROOT = _ROOT.parent

ARTIFACTS_ROOT = _ROOT / "data" / "artifacts"
SCHEMA_VERSION = "1.0"


class ArtifactIO:
    def __init__(self, ticker: str, skill: str) -> None:
        self.ticker = ticker.upper() if not ticker.startswith("_") else ticker
        self.skill = skill
        self.base_dir = ARTIFACTS_ROOT / self.ticker / self.skill
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self.base_dir

    def read_json(self, filename: str) -> dict[str, Any] | None:
        p = self.base_dir / filename
        if not p.exists():
            return None
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def write_json(self, filename: str, data: dict[str, Any]) -> Path:
        data.setdefault("schema_version", SCHEMA_VERSION)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        p = self.base_dir / filename
        with p.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        return p

    def read_text(self, filename: str) -> str | None:
        p = self.base_dir / filename
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8")

    def write_text(self, filename: str, content: str) -> Path:
        p = self.base_dir / filename
        p.write_text(content, encoding="utf-8")
        return p

    def list_files(self, pattern: str = "*") -> list[Path]:
        return sorted(self.base_dir.glob(pattern))


def read_artifact_json(ticker: str, skill: str, filename: str) -> dict[str, Any] | None:
    t = ticker.upper() if not ticker.startswith("_") else ticker
    p = ARTIFACTS_ROOT / t / skill / filename
    if not p.exists():
        return None
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)
