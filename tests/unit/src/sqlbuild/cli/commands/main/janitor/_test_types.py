from dataclasses import dataclass


@dataclass(frozen=True)
class JanitorConfirmationInterruptTestCase:
    description: str
    expected_result: bool
    expected_output_fragments: tuple[str, ...]
    unexpected_output_fragments: tuple[str, ...]
