"""Backward-compatibility shim — delegates to ``pfs.services.investment_report``."""

from pfs.services.investment_report import generate_investment_report

__all__ = ["generate_investment_report"]
