from dataclasses import dataclass


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
