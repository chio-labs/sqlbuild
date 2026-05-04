from dataclasses import dataclass


@dataclass(frozen=True)
class DuckDbRenderCursorBoundLiteralTestCase:
    description: str
    value: str
    cursor_type: str | None
    expected_literal: str
