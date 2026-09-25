from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FitArtifactLogicalNameTestCase:
    description: str
    logical_name: str
    fixed_prefix: str
    identifier_limit: int
    expected_name: str


@dataclass(frozen=True)
class FitArtifactLogicalNameErrorTestCase:
    description: str
    logical_name: str
    fixed_prefix: str
    identifier_limit: int
    expected_error_fragment: str
