from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HiddenCountsTestCase:
    description: str
    allowlisted_pairs: int
    contract_exempt_members: int
    expected_summary_fragment: str


@dataclass(frozen=True)
class ForcedMarkerTestCase:
    description: str
    forced_flags: tuple[bool, ...]
    expected_member_lines: tuple[str, ...]
    expected_json_flags: list[bool]
