from dataclasses import dataclass


@dataclass(frozen=True)
class JanitorConfirmationInterruptTestCase:
    description: str
    expected_result: bool
    expected_output_fragments: tuple[str, ...]
    unexpected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class JanitorDisabledOutputTestCase:
    description: str
    use_color: bool
    expected_output: str | None = None
    expected_prefix: str | None = None


@dataclass(frozen=True)
class JanitorPlanOutputTestCase:
    description: str
    use_color: bool
    expected_output_fragments: tuple[str, ...]
    unexpected_output_fragments: tuple[str, ...] = ()
