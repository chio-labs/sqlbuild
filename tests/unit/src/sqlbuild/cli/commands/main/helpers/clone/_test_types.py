from dataclasses import dataclass

from sqlbuild.virtual.executor.models import VirtualCloneResult


@dataclass(frozen=True)
class RenderVirtualCloneOutputTestCase:
    description: str
    result: VirtualCloneResult
    verbose: bool
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = ()
