"""Generic artifact I/O helpers for skill scripts.

Provides read/write/list utilities for JSON and markdown artifacts stored
under ``data/artifacts/``.  All JSON writes automatically include
``"schema_version": "1.0"`` and ``"updated_at"`` timestamps.

Usage (from within any skill's scripts/ directory)::

    from artifact_io import ArtifactIO

    io = ArtifactIO("_portfolio", "decisions")
    io.write_json("2026-03-31.json", {...})
    data = io.read_json("2026-03-31.json")
    io.write_text("2026-03-31.md", report_md)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
        like ``"_portfolio"`` for non-ticker artifacts.
    skill : str
        Skill name used as the subdirectory (e.g. ``"decisions"``).
    """

    def __init__(self, ticker: str, skill: str) -> None:
        self.ticker = ticker.upper() if not ticker.startswith("_") else ticker
        self.skill = skill
        self.base_dir = ARTIFACTS_ROOT / self.ticker / self.skill
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

    # ── Markdown / text ──────────────────────────────────────────────────

    def write_text(self, filename: str, content: str) -> Path:
        """Write a plain-text / markdown artifact."""
        p = self.base_dir / filename
        with p.open("w", encoding="utf-8") as fh:
            fh.write(content)
        return p

    def read_text(self, filename: str) -> str | None:
        """Read a text artifact, returning ``None`` if missing."""
        p = self.base_dir / filename
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8")

    # ── Listing ──────────────────────────────────────────────────────────

    def list_files(self, suffix: str = "") -> list[str]:
        """List artifact filenames, optionally filtering by suffix."""
        if not self.base_dir.exists():
            return []
        return sorted(
            f.name
            for f in self.base_dir.iterdir()
            if f.is_file() and f.name.endswith(suffix)
        )


def read_artifact_json(
    ticker: str, skill: str, filename: str
) -> dict[str, Any] | None:
    """Convenience: read any skill's artifact without creating an ArtifactIO."""
    io = ArtifactIO(ticker, skill)
    return io.read_json(filename)
