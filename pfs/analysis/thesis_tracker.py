"""Thesis Tracker — backward-compatibility shim.

The canonical implementation now lives in ``skills/_lib/thesis_io.py``.
This module re-exports every public name so that existing imports
(e.g. ``from pfs.analysis.thesis_tracker import create_thesis``) keep working.
"""

from skills._lib.thesis_io import (  # noqa: F401
    get_all_active_theses,
    get_active_thesis,
    get_thesis_detail,
    get_catalysts,
    create_thesis,
    add_thesis_update,
    add_health_check,
    add_catalyst,
    update_catalyst,
    generate_thesis_markdown,
)

__all__ = [
    "get_all_active_theses",
    "get_active_thesis",
    "get_thesis_detail",
    "get_catalysts",
    "create_thesis",
    "add_thesis_update",
    "add_health_check",
    "add_catalyst",
    "update_catalyst",
    "generate_thesis_markdown",
]
