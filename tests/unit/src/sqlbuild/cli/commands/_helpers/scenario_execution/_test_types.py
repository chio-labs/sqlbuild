from dataclasses import dataclass


@dataclass(frozen=True)
class NamespaceCase:
    description: str
    cli: str | None = None
    environment: tuple[tuple[str, str], ...] = ()
    local: str | None = None
    project: str | None = None
    expected_value: str | None = None
    expected_source: str = "unset"


@dataclass(frozen=True)
class InvalidNamespaceCase:
    description: str
    value: object
    expected_error: str = "1–128"


@dataclass(frozen=True)
class InvalidNamespaceConfigCase:
    description: str
    filename: str
    value_toml: str
    expected_error: str = "scenario.run_namespace must be 1–128"


@dataclass(frozen=True)
class SelectScenariosTestCase:
    description: str
    selectors: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_scenario_names: tuple[str, ...]


@dataclass(frozen=True)
class SelectScenariosErrorTestCase:
    description: str
    selectors: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_error_fragment: str
    expected_error_code: str


@dataclass(frozen=True)
class ScenarioCompilePresentationTestCase:
    description: str
    tty: bool
    expected_fragment: str
    unexpected_fragment: str
    expected_terminal: str
