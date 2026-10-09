"""Test case types for compiler engine selection, store namespaces, and stage captures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.compiler.frontier.types import CompilerEngine, CompilerStage, NativeStage


@dataclass(frozen=True)
class EngineResolutionTestCase:
    """One SQLBUILD_COMPILER_ENGINE value and the engine it selects."""

    description: str
    raw_value: str
    expected_engine: CompilerEngine


@dataclass(frozen=True)
class EngineErrorTestCase:
    """One unsupported engine value and the exact error naming accepted values."""

    description: str
    raw_value: str
    expected_message: str


@dataclass(frozen=True)
class EngineOverrideTestCase:
    """An engine variable before an override, and what the override shows and restores."""

    description: str
    previous: str
    override: CompilerEngine
    expected_inside: CompilerEngine
    expected_after: str


@dataclass(frozen=True)
class EngineCacheNameTestCase:
    """One engine and the store directory name it owns."""

    description: str
    engine: CompilerEngine
    base: str
    expected_name: str


@dataclass(frozen=True)
class EngineStorePathsTestCase:
    """One engine and the project-relative compiler and Rules store paths it uses."""

    description: str
    engine: CompilerEngine
    expected_paths: tuple[str, ...]


@dataclass(frozen=True)
class StageCaptureTestCase:
    """One value whose canonical capture must match an exact JSON-compatible shape."""

    description: str
    value: Callable[[], object]
    expected_capture: object


@dataclass(frozen=True)
class StageCaptureOrderTestCase:
    """Two values that differ only in ordering and whether their captures must be identical."""

    description: str
    first: Callable[[], object]
    second: Callable[[], object]
    expected_identical: bool


@dataclass(frozen=True)
class UnorderedAttributeTestCase:
    """Two fill orders for a memo map and an ordered map, and whether captures match."""

    description: str
    first_memo_keys: tuple[str, ...]
    second_memo_keys: tuple[str, ...]
    first_ordered_keys: tuple[str, ...]
    second_ordered_keys: tuple[str, ...]
    expected_identical: bool


@dataclass(frozen=True)
class OmittedFieldTestCase:
    """Dataclass fields left out of a capture, and the capture that remains."""

    description: str
    omitted: frozenset[str]
    expected_capture: object


@dataclass(frozen=True)
class FrontierCaptureTestCase:
    """Frontier stages compiled in order on one engine and the capture files they write."""

    description: str
    engine: CompilerEngine
    stages: tuple[CompilerStage, ...]
    expected_results: tuple[object, ...]
    expected_files: tuple[str, ...]


@dataclass(frozen=True)
class SharedCaptureTestCase:
    """A value with repeated large subtrees and how many distinct shared nodes its capture holds."""

    description: str
    value: Callable[[], object]
    expected_shared_nodes: int


@dataclass(frozen=True)
class NativeStageTierTestCase:
    """One engine, one native stage, and whether that engine runs it."""

    description: str
    engine: CompilerEngine
    stage: NativeStage
    expected_enabled: bool


@dataclass(frozen=True)
class DefaultEngineStageTestCase:
    """With no engine selected, the native stages the default compile runs and those it skips."""

    description: str
    expected_enabled: frozenset[NativeStage]
    expected_disabled: frozenset[NativeStage]
