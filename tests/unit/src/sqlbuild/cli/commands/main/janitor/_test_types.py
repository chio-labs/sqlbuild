from dataclasses import dataclass


@dataclass(frozen=True)
class JanitorPlanOutputTestCase:
    description: str
    use_color: bool
    expected_output_fragments: tuple[str, ...]
    unexpected_output_fragments: tuple[str, ...] = ()
