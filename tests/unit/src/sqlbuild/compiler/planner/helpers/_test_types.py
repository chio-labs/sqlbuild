from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompiledObjectKey


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
