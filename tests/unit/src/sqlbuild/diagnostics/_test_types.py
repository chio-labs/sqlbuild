from dataclasses import dataclass, field


@dataclass(frozen=True)
class DiagnosticsLogTestCase:
    description: str
    debug: bool
    message: str
    expected_file_fragments: tuple[str, ...]
    expected_console_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_absent_file_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_absent_console_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiagnosticsContextualSqlTestCase:
    description: str
    debug: bool
    sql: str
    context: dict[str, str]
    expected_console_fragment: str
