from dataclasses import dataclass


@dataclass(frozen=True)
class FixVerdictTestCase:
    description: str
    before_models: tuple[tuple[str, str], ...]
    after_models: tuple[tuple[str, str], ...]
    edited: tuple[str, ...]
    expected_failing: tuple[tuple[str, str], ...]
    expected_unattributed: bool
