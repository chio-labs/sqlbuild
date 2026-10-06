from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FitAuxiliaryRelationNameTestCase:
    description: str
    base_name: str
    suffix: str
    identifier_limit: int
    expected_name: str


@dataclass(frozen=True)
class FitAuxiliaryRelationNameErrorTestCase:
    description: str
    base_name: str
    suffix: str
    identifier_limit: int
    expected_error_fragment: str
