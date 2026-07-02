from dataclasses import dataclass, field

from sqlbuild.executor.diff.models import DiffExecutionResult


@dataclass(frozen=True)
class DiffOutputIntegrationTestCase:
    description: str
    result: DiffExecutionResult
    mode_label: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)
    verbose: bool = False
    max_column_examples: int = 3
    max_row_only_examples: int = 3
    from_label: str = "prod"
    to_label: str = "dev"
