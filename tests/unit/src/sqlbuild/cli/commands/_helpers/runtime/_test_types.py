from dataclasses import dataclass


@dataclass(frozen=True)
class ModeGuardTestCase:
    description: str
    virtual_environments: bool
    command_name: str
    expected_error_fragment: str | None
    defer_to: str | None = None
    virtual_env: str | None = None
    include_stale_upstreams: bool = False


@dataclass(frozen=True)
class ResolveProjectConnectionConfigTestCase:
    description: str
    project_dir_name: str
    expected_connection: dict[str, object]
    expected_warning_fragment: str = ""


@dataclass(frozen=True)
class ResolveEnvironmentConnectionConfigTestCase:
    description: str
    target_name: str
    expected_connection: dict[str, object]


@dataclass(frozen=True)
class ResolveConnectionConfigWarningTestCase:
    description: str
    raw_config: dict[str, object]
    adapter_name: str
    expected_connection: dict[str, object]
    expected_warning: str


@dataclass(frozen=True)
class ResolveDbtProfileConnectionConfigTestCase:
    description: str
    raw_config: dict[str, object]
    profile_connection: dict[str, object]
    expected_connection: dict[str, object]


@dataclass(frozen=True)
class NamedConnectionBehaviorTestCase:
    description: str
    expected_connection: dict[str, object]
    expected_error_fragment: str | None = None
