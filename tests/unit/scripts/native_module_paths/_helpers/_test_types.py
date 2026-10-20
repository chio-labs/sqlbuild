from dataclasses import dataclass


@dataclass(frozen=True)
class NativeSourceModulePathTestCase:
    description: str
    source: str
    expected_errors: tuple[str, ...]


@dataclass(frozen=True)
class RepositoryModulePathTestCase:
    description: str
    expected_errors: tuple[str, ...]
    expected_logger_names: tuple[str, ...]


@dataclass(frozen=True)
class HostTableCase:
    description: str
    expected_duplicate_count: int
    expected_missing_names: tuple[str, ...]
    expected_extra_names: tuple[str, ...]


@dataclass(frozen=True)
class HostKindCase:
    description: str
    expected_mismatched_names: tuple[str, ...]


@dataclass(frozen=True)
class HostImportCase:
    description: str
    expected_loaded_modules: tuple[str, ...]


@dataclass(frozen=True)
class HostUnknownNameCase:
    description: str
    name: str
    expected_error: str


@dataclass(frozen=True)
class HostDeadCodeRootCase:
    description: str
    expected_missing_targets: tuple[tuple[str, str], ...]
    expected_extra_targets: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class HostResultMirrorCase:
    description: str
    expected_mirror_count: int
    expected_mismatches: tuple[str, ...]
