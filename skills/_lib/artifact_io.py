"""Generic artifact I/O helpers for skill scripts.

Provides read/write/list utilities for JSON and markdown artifacts stored
under ``data/artifacts/``.  All JSON writes automatically include
``"schema_version": "1.0"`` and ``"updated_at"`` timestamps.

Usage::

    from skills._lib.artifact_io import ArtifactIO

    io = ArtifactIO("NVDA", "profile")
    io.write_json("company_overview.json", {"name": "NVIDIA", ...})
    data = io.read_json("company_overview.json")
    io.write_text("company_report.md", report_md)
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
        like ``"_etl"`` for non-ticker artifacts.
    skill : str
        Skill name used as the subdirectory (e.g. ``"profile"``, ``"thesis"``).
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
        """Write a JSON artifact with schema_version and updated_at metadata.

        Returns the path of the written file.
        """
        data.setdefault("schema_version", SCHEMA_VERSION)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        p = self.base_dir / filename
        with p.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        return p

    def append_to_json_list(
        self,
        filename: str,
        entry: dict[str, Any],
        *,
        list_key: str = "entries",
    ) -> Path:
        """Append *entry* to a JSON file that stores an array under *list_key*.

        Creates the file if it doesn't exist.  Useful for append-only logs
        like ``updates.json`` or ``health_checks.json``.
        """
        existing = self.read_json(filename) or {
            "schema_version": SCHEMA_VERSION,
            list_key: [],
        }
        existing.setdefault(list_key, [])
        existing[list_key].append(entry)
        return self.write_json(filename, existing)

    # ── Text / Markdown ──────────────────────────────────────────────────

    def read_text(self, filename: str) -> str | None:
        """Read a text/markdown artifact, returning ``None`` if missing."""
        p = self.base_dir / filename
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8")

    def write_text(self, filename: str, content: str) -> Path:
        """Write a text/markdown artifact and return its path."""
        p = self.base_dir / filename
        p.write_text(content, encoding="utf-8")
        return p

    # ── Listing / Existence ──────────────────────────────────────────────

    def exists(self, filename: str) -> bool:
        """Check if an artifact file exists."""
        return (self.base_dir / filename).exists()

    def list_files(self, pattern: str = "*") -> list[Path]:
        """List files in the artifact directory matching *pattern*."""
        return sorted(self.base_dir.glob(pattern))

    def file_path(self, filename: str) -> Path:
        """Return the full path for *filename* (may not exist yet)."""
        return self.base_dir / filename


# ── Convenience functions (non-OO) ───────────────────────────────────────────


def read_artifact_json(
    ticker: str, skill: str, filename: str
) -> dict[str, Any] | None:
    """Read a single JSON artifact without constructing an ArtifactIO."""
    return ArtifactIO(ticker, skill).read_json(filename)


def write_artifact_json(
    ticker: str, skill: str, filename: str, data: dict[str, Any]
) -> Path:
    """Write a single JSON artifact without constructing an ArtifactIO."""
    return ArtifactIO(ticker, skill).write_json(filename, data)


def read_artifact_text(ticker: str, skill: str, filename: str) -> str | None:
    """Read a single text artifact without constructing an ArtifactIO."""
    return ArtifactIO(ticker, skill).read_text(filename)


def write_artifact_text(
    ticker: str, skill: str, filename: str, content: str
) -> Path:
    """Write a single text artifact without constructing an ArtifactIO."""
    return ArtifactIO(ticker, skill).write_text(filename, content)
