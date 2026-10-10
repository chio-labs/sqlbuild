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
class NativeYamlLoadTestCase:
    """Source files whose native load outcomes and loaded values are checked."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    expected_native_tags: tuple[str, ...]


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
class UndecodableDeclarationNameTestCase:
    """A declaration file whose path holds a name that is not UTF-8, which discovery rejects."""

    description: str
    relative_path: bytes
    contents: bytes
    expected_path: str


@dataclass(frozen=True)
class GeneratedDeclarationFileTestCase:
    """Seeded declaration files of one kind discovered by the Python and native-preview engines."""

    description: str
    kind: str
    relative_path: str
    case_count: int
    expected_minimum_parsed: int
    expected_minimum_failed: int
    expected_maximum_deferred: int
    expected_mismatches: tuple[int, ...] = ()


@dataclass(frozen=True)
class DeclarationFilesParityTestCase:
    """A project whose declaration files discovery reads under the Python and preview engines."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    expected_failure_type: str = "NoneType"
    expected_message_fragment: str = ""


@dataclass(frozen=True)
class NativeSessionTestCase:
    """Whether a discovery pass under one engine keeps its native declaration session."""

    description: str
    engine: str
    expected_session: bool


@dataclass(frozen=True)
class TolerantDeclarationFilesTestCase:
    """A project whose broken declaration files tolerant scope discovery reports as faults."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    expected_resource_faults: int
    expected_declaration_faults: int


@dataclass(frozen=True)
class FailureTextTestCase:
    """A project whose discovery failure message must keep its authored text unchanged."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    expected_error_type: str
    expected_message_suffix: str


@dataclass(frozen=True)
class TolerantFailureTextTestCase:
    """A project whose broken declaration files tolerant discovery faults with authored text."""

    description: str
    files: tuple[tuple[str, bytes], ...]
    expected_fault_keys: tuple[str, ...]


@dataclass(frozen=True)
class DeepDeclarationHeaderTestCase:
    """A declaration file whose header nests one value `depth` levels deep."""

    description: str
    kind: str
    relative_path: str
    prefix: str
    suffix: str
    depth: int
    expected_failure_type: str
    expected_message_suffix: str
    expected_help: str = "flatten the value so it nests at most 256 levels deep"


@dataclass(frozen=True)
class DeepHeaderValuesTestCase:
    """A model header whose values reach the nesting limit, discovered on a deep Python stack."""

    description: str
    header: str
    stack_frames: int
    expected_engines: tuple[str, ...]
    expected_max_depth: int
