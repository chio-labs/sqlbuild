from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlbuild.cli.commands.models import DiffExampleRenderOptions
from sqlbuild.executor.diff.models import DiffExecutionResult, FullDiffSizeLimits


@dataclass(frozen=True)
class RenderDiffOutputTestCase:
    description: str
    result: DiffExecutionResult
    from_label: str
    to_label: str
    mode_label: str
    verbose: bool
    max_column_examples: int
    max_row_only_examples: int
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class RenderDiffEvidenceTestCase:
    description: str
    left_value: object
    right_value: object
    options: DiffExampleRenderOptions
    expected_left_fragment: str
    expected_right_fragment: str
    expected_first_difference: int | None
    expected_truncated: bool
    expected_suppressed: bool


@dataclass(frozen=True)
class FullDiffSizeLimitsTestCase:
    description: str
    full: bool
    schema_only: bool
    bounded: str | None
    prod_max_full_rows: int | Literal["unlimited"] | None
    dev_max_full_rows: int | Literal["unlimited"] | None
    expected_limits: FullDiffSizeLimits | None


@dataclass(frozen=True)
class DiffSizeGuardErrorTestCase:
    description: str
    select: tuple[str, ...]
    unique_key_override: tuple[str, ...]
    has_cursor: bool
    expected_full_command: str
    expected_bounded_command: str | None
    expected_message_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...] = ()
    project_dir: Path | None = None


@dataclass(frozen=True)
class ParseDiffNameRangeTestCase:
    description: str
    name_range: str
    expected_result: tuple[str, str | None]


@dataclass(frozen=True)
class ParseDiffNameRangeErrorTestCase:
    description: str
    name_range: str | None
    expected_code: str
