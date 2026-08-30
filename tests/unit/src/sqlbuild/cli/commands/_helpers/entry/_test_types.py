from dataclasses import dataclass


@dataclass(frozen=True)
class VerboseCommandTestCase:
    """One command that supports verbose output."""

    description: str
    expected_argv: tuple[str, ...]
