from dataclasses import dataclass

from sqlbuild.adapter.shared.models import SchemaDiffResult


@dataclass(frozen=True)
class SnowflakeRenderCursorBoundLiteralTestCase:
    description: str
    value: str
    cursor_type: str | None
    expected_literal: str


@dataclass(frozen=True)
class SnowflakeSchemaDiffTestCase:
    description: str
    expected_result: SchemaDiffResult
