from dataclasses import dataclass


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
