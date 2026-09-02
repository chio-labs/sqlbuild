from dataclasses import dataclass


@dataclass(frozen=True)
class EventExporterE2ETestCase:
    description: str
    expected_first_event: str


@dataclass(frozen=True)
class NoExporterCommandE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_exit_code: int


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


@dataclass(frozen=True)
class ProviderCommandConcurrencyE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_marker_entries: tuple[str, ...]
    expected_exit_code: int


@dataclass(frozen=True)
class ProviderHookE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_marker_entries: tuple[str, ...]
    expected_exit_code: int


@dataclass(frozen=True)
class ProviderHookDiagnosticE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class ProviderHookMaterializationE2ETestCase:
    description: str
    command: tuple[str, ...]
    model_relative_path: str
    model_sql: str
    extra_repo_files: dict[str, str]
    expected_marker_entries: tuple[str, ...]
    expected_exit_code: int


@dataclass(frozen=True)
class ProviderHookContextConflictE2ETestCase:
    description: str
    command: tuple[str, ...]
    context_parameter_name: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ProviderPlanOutputE2ETestCase:
    description: str
    expected_text_fragments: tuple[str, ...]
    expected_provider_name: str
    expected_used_by: tuple[tuple[str, str, str], ...]
