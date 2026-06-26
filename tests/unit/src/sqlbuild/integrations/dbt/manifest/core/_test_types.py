from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DbtConfigStripTestCase:
    description: str
    raw_code: str
    expected_body_line: str
    expected_absent_fragment: str
