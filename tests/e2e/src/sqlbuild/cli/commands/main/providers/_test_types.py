from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCommandE2ETestCase:
    description: str
    expected_exit_code: int
    expected_marker_entries: tuple[str, ...]
    expected_loaded_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ProviderCommandFailureE2ETestCase:
    description: str
    command: tuple[str, ...]
    repo_files: dict[str, str]
    expected_marker_entries: tuple[str, ...]


@dataclass(frozen=True)
class ProviderCommandSideEffectE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_marker_exists: bool


@dataclass(frozen=True)
class ProviderCommandDiagnosticE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class ProviderCustomMaterializationE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_marker_entries: tuple[str, ...]
    expected_exit_code: int
