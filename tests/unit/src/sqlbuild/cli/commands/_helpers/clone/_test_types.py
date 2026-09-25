from dataclasses import dataclass

from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult


@dataclass(frozen=True)
class RenderCloneOutputTestCase:
    description: str
    result: CloneExecutionResult
    expected_fragments: tuple[str, ...]
    expected_color_fragments: tuple[str, ...] = ()
    unexpected_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderCloneItemLineTestCase:
    description: str
    index: int
    total: int
    item: CloneItemResult
    expected_fragments: tuple[str, ...]
    expected_line: str
    relation_width: int | None = None
    unexpected_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class CloneConnectionLifecycleTestCase:
    description: str
    expected_destination_config: dict[str, object]


@dataclass(frozen=True)
class RenderCloneFingerprintProgressTestCase:
    description: str
    completed: int
    total: int
    expected_line: str


@dataclass(frozen=True)
class RenderCloneFingerprintInterruptedTestCase:
    description: str
    completed: int
    total: int
    pending_identities: tuple[str, ...]
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CloneFingerprintProgressReporterTestCase:
    description: str
    completed: int
    total: int
    pending_identities: tuple[str, ...]
    expected_fragments: tuple[str, ...]
