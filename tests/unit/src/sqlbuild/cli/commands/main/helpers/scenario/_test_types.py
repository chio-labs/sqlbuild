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
class ScenarioRunOutputTestCase:
    description: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioCaptureOutputTestCase:
    description: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = ()
