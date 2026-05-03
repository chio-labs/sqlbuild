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
