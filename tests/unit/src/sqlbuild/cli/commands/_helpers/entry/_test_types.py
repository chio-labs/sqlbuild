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


@dataclass(frozen=True)
class GlobalFlagPlacementTestCase:
    """One placement of the flags every command accepts."""

    description: str
    argv: tuple[str, ...]
    expected_debug: bool
    expected_no_color: bool
    expected_project_dir: str | None


@dataclass(frozen=True)
class PositionalSelectTestCase:
    """Selectors given as positional arguments, alone or with --select."""

    description: str
    argv: tuple[str, ...]
    expected_select: tuple[str, ...]


@dataclass(frozen=True)
class OutputFormatAliasTestCase:
    """A --json alias for a command whose output format is chosen with --format."""

    description: str
    argv: tuple[str, ...]
    format_attribute: str
    expected_format: str


@dataclass(frozen=True)
class RejectedArgumentsTestCase:
    """Arguments the parser must reject with a usage error."""

    description: str
    argv: tuple[str, ...]
    expected_message: str


@dataclass(frozen=True)
class DbtProjectDirParsingTestCase:
    """A dbt command whose --project-dir belongs to dbt rather than SQLBuild."""

    description: str
    argv: tuple[str, ...]
    expected_dbt_project_dir: str | None
    expected_dbt_args: tuple[str, ...]
    expected_no_color: bool


@dataclass(frozen=True)
class UntypedCursorParsingTestCase:
    """Untyped --start-cursor/--end-cursor flags kept raw for the planner to type."""

    description: str
    argv: tuple[str, ...]
    expected_start: str | None
    expected_end: str | None
