from __future__ import annotations

import sys
import unicodedata
from dataclasses import dataclass, field


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
class NativeRuntimeTestCase:
    """A project and runtime under which native model discovery runs or fails clearly."""

    description: str
    project_name: str
    expected_models: int
    expected_error: str = "NoneType"
    expected_message: str = "None"
    unidata_version: str = field(default_factory=lambda: unicodedata.unidata_version)
    python_version: tuple[int, int] = field(
        default_factory=lambda: (sys.version_info[0], sys.version_info[1])
    )


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
    """Source files whose native load outcomes and loaded values are checked."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    expected_native_tags: tuple[str, ...]


@dataclass(frozen=True)
class EntryPointParityTestCase:
    """Authored files read through a bounded discovery entry point by both implementations."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    expected_identical: bool = True


@dataclass(frozen=True)
class ReadErrorOracleTestCase:
    """Seeded byte strings whose native read error must equal Python's `read_text` error."""

    description: str
    seed: int
    case_count: int
    expected_minimum_failures: int


@dataclass(frozen=True)
class UnreadableFileTestCase:
    """One unreadable authored file that compile reports with Python's own read error."""

    description: str
    relative_path: str
    data: bytes
    expected_error: str
    expected_message: str


@dataclass(frozen=True)
class AuthoredFileFailureTestCase:
    """Authored files that discovery reads, or rejects with one clear error."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    expected_error: str = "NoneType"
    expected_message: str = "None"
    expected_help: bool = False


@dataclass(frozen=True)
class UndecodablePathToleranceTestCase:
    """A project with names that are not UTF-8, read by a caller that tolerates bad files."""

    description: str
    reader: str
    files: tuple[tuple[str, bytes], ...]
    expected_models: tuple[str, ...]
    expected_sources: tuple[str, ...]
    expected_faults: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class UnsupportedPythonCommandTestCase:
    """A command run on a Python this release does not support."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_error: str


@dataclass(frozen=True)
class NativeOsErrorTestCase:
    """An operating-system read payload and the Python error it becomes."""

    description: str
    payload: tuple[object, ...]
    expected_type: str
    expected_fields: tuple[object, ...]


@dataclass(frozen=True)
class CollidingNamesTestCase:
    """Files whose names are not UTF-8 but share a lossy spelling, each keeping its own identity."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    expected_enums: tuple[tuple[str, tuple[str, ...]], ...]
    expected_models: tuple[str, ...] = ("models/orders.sql",)
