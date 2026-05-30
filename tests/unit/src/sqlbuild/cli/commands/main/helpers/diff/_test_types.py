from dataclasses import dataclass

from sqlbuild.executor.diff.models import DiffExecutionResult


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
class RenderVirtualDiffHeaderTestCase:
    description: str
    selected_names: tuple[str, ...]
    skipped_names: tuple[str, ...]
    from_stale: tuple[str, ...]
    to_stale: tuple[str, ...]
    from_working: bool
    to_working: bool
    allow_partial_diff: bool
    verbose: bool
    expected_fragments: tuple[str, ...]
    expected_color_fragments: tuple[str, ...] = ()
    unexpected_fragments: tuple[str, ...] = ()
