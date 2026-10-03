"""Sensitive-data layer on top of Laya (open Jev-class classifier)."""

from .layer import SensitiveDataBlocked, SensitiveDataLayer, scan_text
from .models import CategorySummary, Entity, ProtectResult, ScanResult
from .taxonomy import GateAction, RiskLevel, SensitivityCategory

__all__ = [
    "CategorySummary",
    "Entity",
    "GateAction",
    "ProtectResult",
    "RiskLevel",
    "ScanResult",
    "SensitivityCategory",
    "SensitiveDataBlocked",
    "SensitiveDataLayer",
    "scan_text",
]

__version__ = "0.1.0"
