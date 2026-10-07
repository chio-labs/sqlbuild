from __future__ import annotations

from dataclasses import dataclass, field

import sqlbuild._native as _native


@dataclass(frozen=True)
class GeneratedDocumentOracleTestCase:
    """Seeded generated documents loaded natively and by the Python library they mirror."""

    description: str
    generator: str
    seed: int
    case_count: int
    expected_maximum_deferred: int
    expected_mismatches: tuple[tuple[object, object, object], ...] = ()


@dataclass(frozen=True)
class RepositoryFileOracleTestCase:
    """Repository files of one kind loaded natively and by the Python loader."""

    description: str
    pattern: str
    expected_minimum_files: int
    expected_deferred: int = 0
    expected_mismatches: tuple[tuple[object, object, object], ...] = ()


@dataclass(frozen=True)
class HostileDocumentOracleTestCase:
    """A document built to exhaust a naive reader, which the native reader must defer quickly."""

    description: str
    document: str
    expected_deferred: bool = True
    expected_maximum_seconds: float = 1.0


@dataclass(frozen=True)
class LargeDocumentOracleTestCase:
    """A large single-line document that must load in linear time with PyYAML's value."""

    description: str
    document: str
    expected_maximum_seconds: float = 2.0


@dataclass(frozen=True)
class ModelDiscoveryParityTestCase:
    """Authored model files discovered by both compiler engines."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    directories: tuple[str, ...] = ()
    expected_identical: bool = True


@dataclass(frozen=True)
class GeneratedModelParityTestCase:
    """Seeded model files discovered by both compiler engines, one file at a time."""

    description: str
    seed: int
    case_count: int
    expected_mismatches: tuple[tuple[object, object, object], ...] = ()


@dataclass(frozen=True)
class EngineSwitchParityTestCase:
    """A project discovered through `discover_project_inputs` under each engine."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    expected_identical: bool = True


@dataclass(frozen=True)
class NativeDeferralTestCase:
    """A project and runtime under which native model discovery must or must not run."""

    description: str
    project_name: str
    expected_native_calls: int
    unidata_version: str = field(default_factory=lambda: _native.PYTHON_ALNUM_UNICODE_VERSION)


@dataclass(frozen=True)
class SharedSnapshotTestCase:
    """A file created after native model discovery, inside the same discovery pass."""

    description: str
    created_file: str
    pattern: str
    expected_matches: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedLayoutParityTestCase:
    """Seeded declaration layouts whose native validation and facts must match Python's."""

    description: str
    seed: int
    count: int
    expected_mismatches: tuple[str, ...] = ()
    expected_minimum_valid: int = 0
    expected_minimum_invalid: int = 0


@dataclass(frozen=True)
class GeneratedSqlTestParityTestCase:
    """Seeded SQL test and scenario files discovered by both compiler engines."""

    description: str
    seed: int
    case_count: int
    expected_mismatches: tuple[tuple[object, object, object], ...] = ()
    expected_minimum_parsed: int = 0
    expected_minimum_failed: int = 0


@dataclass(frozen=True)
class GeneratedYamlFileParityTestCase:
    """Seeded source and seed declaration files discovered by both compiler engines."""

    description: str
    seed: int
    case_count: int
    expected_mismatches: tuple[tuple[object, object, object], ...] = ()
    expected_minimum_parsed: int = 0
    expected_minimum_failed: int = 0


@dataclass(frozen=True)
class NativeYamlLoadTestCase:
    """Source files whose native load outcome and engine parity are both checked."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    expected_native_tags: tuple[str, ...]


@dataclass(frozen=True)
class FactCacheFallbackTestCase:
    """A runtime under which native source and test discovery must use the fact cache or not."""

    description: str
    unidata_version: str
    expected_same_keys_as_python: bool
    expected_native_keys: int
