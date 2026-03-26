"""Backward-compatibility shim — delegates to ``pfs.services.splits``.

Usage::

    from pfs.splits import get_split_adjustor
"""

from pfs.services.splits import (
    cumulative_split_factor,
    get_split_adjustor,
    load_splits_from_db,
)

__all__ = ["cumulative_split_factor", "get_split_adjustor", "load_splits_from_db"]
