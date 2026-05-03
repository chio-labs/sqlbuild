from dataclasses import dataclass

from sqlbuild.executor.diff.models import DiffExecutionResult


@dataclass(frozen=True)
class RenderDiffOutputTestCase:
    description: str
    result: DiffExecutionResult
    from_label: str
    to_label: str
    mode_label: str
    expected_fragments: tuple[str, ...]
