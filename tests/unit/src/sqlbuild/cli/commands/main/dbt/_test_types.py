from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DbtPlanProgressTestCase:
    description: str
    json_output: bool
    expected_stdout_fragments: tuple[str, ...]
    expected_stderr_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtExecutionWrapperTestCase:
    description: str
    command_name: str
    args: tuple[str, ...]
    expected_forwarded_args: tuple[str, ...]
    expected_progress_stream_name: str
