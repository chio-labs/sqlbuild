from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DbtPlanProgressTestCase:
    description: str
    json_output: bool
    expected_stdout_fragments: tuple[str, ...]
    expected_stderr_fragments: tuple[str, ...]
