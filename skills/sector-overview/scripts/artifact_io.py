"""Generic artifact I/O helpers for sector-overview skill scripts.

Provides read/write/list utilities for JSON and markdown artifacts stored
under ``data/artifacts/``.  All JSON writes automatically include
``"schema_version": "1.0"`` and ``"updated_at"`` timestamps.

Usage::

    from artifact_io import ArtifactIO

    io = ArtifactIO("_sectors", "technology")
    io.write_json("sector_data.json", {...})
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def slugify(sector: str) -> str:
    """Convert sector name to a URL-safe slug."""
    s = sector.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

# ── Locate project root ─────────────────────────────────────────────────────

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent
for _ in range(6):
    if (_ROOT / "data" / "artifacts").exists():
        break
    _ROOT = _ROOT.parent

ARTIFACTS_ROOT = _ROOT / "data" / "artifacts"

SCHEMA_VERSION = "1.0"


class ArtifactIO:
    """Read/write helper scoped to a skill's artifact directory.

    Parameters
    ----------
    ticker : str
        Company ticker (uppercased automatically), or a special prefix
        like ``"_sectors"`` for non-ticker artifacts.
    skill : str
        Skill name used as the subdirectory (e.g. ``"technology"``).
    """

    def __init__(self, ticker: str, skill: str) -> None:
        self.ticker = ticker.upper() if not ticker.startswith("_") else ticker
        self.skill = skill
        if skill:
            self.base_dir = ARTIFACTS_ROOT / self.ticker / self.skill
        else:
            self.base_dir = ARTIFACTS_ROOT / self.ticker
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        """Return the base directory path."""
        return self.base_dir

    # ── JSON ─────────────────────────────────────────────────────────────

    def read_json(self, filename: str) -> dict[str, Any] | None:
        """Read a JSON artifact, returning ``None`` if the file is missing."""
        p = self.base_dir / filename
        if not p.exists():
            return None
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def write_json(self, filename: str, data: dict[str, Any]) -> Path:
        """Write a JSON artifact with schema_version and updated_at metadata."""
        data.setdefault("schema_version", SCHEMA_VERSION)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        p = self.base_dir / filename
        with p.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        return p

    # ── Markdown ─────────────────────────────────────────────────────────

    def read_text(self, filename: str) -> str | None:
        """Read a text artifact, returning ``None`` if the file is missing."""
        p = self.base_dir / filename
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8")

    def write_text(self, filename: str, content: str) -> Path:
        """Write a text/markdown artifact."""
        p = self.base_dir / filename
        p.write_text(content, encoding="utf-8")
        return p

    def list_files(self, pattern: str = "*") -> list[Path]:
        """List files in the artifact directory matching a glob pattern."""
        return sorted(self.base_dir.glob(pattern))


def read_artifact_json(ticker: str, skill: str, filename: str) -> dict[str, Any] | None:
    """Convenience function to read a single artifact JSON file."""
    io = ArtifactIO(ticker, skill)
    return io.read_json(filename)
