from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestrE2ETestCase:
    description: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...]
