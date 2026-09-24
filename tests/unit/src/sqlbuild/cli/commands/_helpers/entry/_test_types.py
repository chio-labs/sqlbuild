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


@dataclass(frozen=True)
class VersionFlagTestCase:
    """One --version invocation shape."""

    description: str
    argv: tuple[str, ...]
    expected_exit_code: int


@dataclass(frozen=True)
class QueryDiffParsingTestCase:
    description: str
    argv: tuple[str, ...]
    expected_left_query: str | None
    expected_right_query: str | None
    expected_keys: tuple[str, ...]
    expected_unkeyed: bool


@dataclass(frozen=True)
class EventExportWarningTestCase:
    description: str
    exporter_counts: tuple[tuple[str, int, int, int, int], ...]
    command_succeeded: bool
    expected_message: str | None
