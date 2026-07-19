from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildReportTestCase:
    description: str
    expected_top_pair: tuple[str, str]
    expected_signal_names: tuple[str, ...]


@dataclass(frozen=True)
class ReportDeltaTestCase:
    description: str
    expected_new_twin_fragment: str
