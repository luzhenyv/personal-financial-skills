"""Backward-compatibility shim — delegates to ``pfs.services.comps``."""

from pfs.services.comps import (
    build_comps,
    compute_summary,
    discover_peers,
    fetch_peer_data,
)

__all__ = ["build_comps", "compute_summary", "discover_peers", "fetch_peer_data"]
