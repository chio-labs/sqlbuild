from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SqlglotImportTestCase:
    description: str
    missing_module_name: str
    expected_available: bool
