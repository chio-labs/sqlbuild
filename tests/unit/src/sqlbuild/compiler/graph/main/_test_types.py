from dataclasses import dataclass


@dataclass(frozen=True)
class InvertEdgesTestCase:
    description: str
    edges: dict[str, tuple[str, ...]]
    expected_edges: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class TransitiveClosureTestCase:
    description: str
    edges: dict[str, tuple[str, ...]]
    start: str
    max_depth: int | None
    expected_nodes: frozenset[str]


@dataclass(frozen=True)
class TransitiveClosureManyTestCase:
    description: str
    edges: dict[str, tuple[str, ...]]
    starts: tuple[str, ...]
    include_starts: bool
    expected_nodes: frozenset[str]
    max_depth: int | None = None


@dataclass(frozen=True)
class PathNodesTestCase:
    description: str
    downstream: dict[str, tuple[str, ...]]
    start: str
    end: str
    expected_nodes: frozenset[str] | None
