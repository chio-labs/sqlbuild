from dataclasses import dataclass


@dataclass(frozen=True)
class VerboseCommandTestCase:
    """One command that supports verbose output."""

    description: str
    expected_argv: tuple[str, ...]


@dataclass(frozen=True)
class AuditConcurrencyParsingTestCase:
    description: str
    argv: tuple[str, ...]
    environment_value: str | None
    expected_concurrency: int | None
    expected_exit_code: int | None
