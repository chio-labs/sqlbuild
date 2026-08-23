from dataclasses import dataclass


@dataclass(frozen=True)
class CursorIntrinsicValidationTestCase:
    description: str
    sql: str
    expected_sql: str


@dataclass(frozen=True)
class CursorIntrinsicRenderTestCase:
    description: str
    sql: str
    expected_sql: str


@dataclass(frozen=True)
class CursorIntrinsicErrorTestCase:
    description: str
    sql: str
    expected_error_fragment: str


@dataclass(frozen=True)
class CursorIntrinsicAnalysisTestCase:
    description: str
    cursor_type: str
    expected_type: str
