"""Backward-compatibility shim — delegates to ``pfs.services.analysis``."""

from pfs.services.analysis import get_profile_data, generate_tearsheet

__all__ = ["get_profile_data", "generate_tearsheet"]
