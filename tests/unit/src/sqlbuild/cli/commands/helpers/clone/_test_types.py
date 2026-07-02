from dataclasses import dataclass

from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.virtual.executor.models import VirtualCloneResult


@dataclass(frozen=True)
class RenderVirtualCloneOutputTestCase:
    description: str
    result: VirtualCloneResult
    verbose: bool
    expected_fragments: tuple[str, ...]
    expected_color_fragments: tuple[str, ...] = ()
    unexpected_fragments: tuple[str, ...] = ()


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
    unexpected_fragments: tuple[str, ...] = ()
