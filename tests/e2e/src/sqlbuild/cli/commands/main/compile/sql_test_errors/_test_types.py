from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeSqlTestErrorTestCase:
    """One failing SQL test, scenario or relationship project compiled through the CLI."""

    description: str
    case_name: str
    expected_location: str = ""
