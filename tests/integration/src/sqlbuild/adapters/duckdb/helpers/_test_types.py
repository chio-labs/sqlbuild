from dataclasses import dataclass

from sqlbuild.adapter.models import CursorValue


@dataclass(frozen=True)
class BuildAttachSqlTestCase:
    description: str
    attach_entry: dict[str, object]
    expected_sql: str


@dataclass(frozen=True)
class BuildCursorFilterTestCase:
    description: str
    cursor_column: str | None
    start_cursor: CursorValue | None
    end_cursor: CursorValue | None
    expected_filter: str
