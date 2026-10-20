from dataclasses import dataclass, field


@dataclass(frozen=True)
class DiagnosticsLogTestCase:
    description: str
    debug: bool
    message: str
    expected_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_console_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_absent_console_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiagnosticsContextualSqlTestCase:
    description: str
    debug: bool
    sql: str
    context: dict[str, str]
    expected_console_fragment: str


@dataclass(frozen=True)
class ProcessResourceTestCase:
    description: str
    monotonic_values: tuple[float, float]
    resource_values: tuple[tuple[float, float, int | None], ...]
    expected_wall_seconds: float
    expected_user_cpu_seconds: float
    expected_system_cpu_seconds: float
    expected_max_rss_bytes: int | None


@dataclass(frozen=True)
class ConsoleDurationTestCase:
    description: str
    subject: object
    duration_ms: object
    expected_line: str


@dataclass(frozen=True)
class ThirdPartyConsoleTestCase:
    description: str
    debug: bool
    expected_console_lines: tuple[str, ...]
    expected_traceback_count: int


@dataclass(frozen=True)
class ConsoleProgressLineTestCase:
    description: str
    message: str
    expected_log_line: str
