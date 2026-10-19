from dataclasses import dataclass, field


@dataclass(frozen=True)
class SqliteOracleE2ETestCase:
    description: str
    compared_models: tuple[tuple[str, str], ...]
    unexpected_rebuild_fragments: tuple[str, ...]
    expected_return_code: int = 0


@dataclass(frozen=True)
class SqliteCommandE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_fragments: tuple[str, ...]
    expected_return_code: int = 0


@dataclass(frozen=True)
class SqliteFileLayoutE2ETestCase:
    description: str
    expected_tables: tuple[str, ...]
    absent_tables: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SqliteProjectE2ETestCase:
    description: str
    files: dict[str, str]
    changed_files: dict[str, str]
    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    absent_tables: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class SqliteFailureE2ETestCase:
    description: str
    files: dict[str, str]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SqliteLockE2ETestCase:
    description: str
    busy_timeout: float
    hold_seconds: float
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SqliteScenarioE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_outcomes: dict[str, tuple[str, str | None]]
    expected_tables: tuple[str, ...]
    expected_return_code: int = 1
