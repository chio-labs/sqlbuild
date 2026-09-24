from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HiddenCountsTestCase:
    description: str
    allowlisted_pairs: int
    contract_exempt_members: int
    expected_summary_fragment: str
