from __future__ import annotations

from dataclasses import dataclass

from scripts.dupscore.models import ContractExemptionEntry


@dataclass(frozen=True)
class ForcedOverrideTestCase:
    description: str
    language: str
    path: str
    name: str
    expected_forced: bool


@dataclass(frozen=True)
class ContractLookupErrorTestCase:
    description: str
    entry: ContractExemptionEntry
    expected_error_fragment: str


@dataclass(frozen=True)
class InactiveContractTestCase:
    description: str
    entry: ContractExemptionEntry
    path: str
    name: str
    expected_forced: bool
