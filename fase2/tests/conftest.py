"""Garante import de quality/validations sem boto3 no venv da Fase 2."""

from __future__ import annotations

import sys
from types import ModuleType

try:
    import boto3  # noqa: F401
except ImportError:
    boto3 = ModuleType("boto3")
    boto3.client = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    sys.modules["boto3"] = boto3
