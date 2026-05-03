from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner.models import MissingUpstream, ParsedSelector


@dataclass(frozen=True)
class BuildUpstreamDepsTestCase:
    description: str
    model_deps: dict[str, tuple[str, ...]]
    source_names: tuple[str, ...]
    seed_names: tuple[str, ...]
    expected_upstream_keys: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class BuildDownstreamDepsTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_downstream_keys: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]


@dataclass(frozen=True)
class TopologicalOrderTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_order: tuple[CompiledObjectKey, ...]


@dataclass(frozen=True)
class CycleDetectionTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_error_type: type[Exception]


@dataclass(frozen=True)
class ExpandUpstreamTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    key: CompiledObjectKey
    expected_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class ExpandDownstreamTestCase:
    description: str
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    key: CompiledObjectKey
    expected_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class FindPathKeysTestCase:
    description: str
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    start: CompiledObjectKey
    end: CompiledObjectKey
    expected_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class FindPathKeysErrorTestCase:
    description: str
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    start: CompiledObjectKey
    end: CompiledObjectKey
    expected_error_type: type[Exception]


@dataclass(frozen=True)
class ParseSelectorTestCase:
    description: str
    raw: str
    expected_result: ParsedSelector | tuple[str, str]


@dataclass(frozen=True)
class ParseSelectorErrorTestCase:
    description: str
    raw: str
    expected_error_type: type[Exception]


@dataclass(frozen=True)
class ResolveSelectorTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_names: frozenset[str]


@dataclass(frozen=True)
class ResolveSelectorErrorTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_error_type: type[Exception]


@dataclass(frozen=True)
class CheckBuildabilityTestCase:
    description: str
    selected_keys: frozenset[CompiledObjectKey]
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    existing_relation_names: tuple[str, ...]
    expected_missing: tuple[MissingUpstream, ...]
