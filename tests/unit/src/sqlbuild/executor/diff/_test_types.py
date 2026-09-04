from dataclasses import dataclass

from sqlbuild.adapter.contract.models import CursorValue, RowDiffTolerances


@dataclass(frozen=True)
class ParseRowDiffTolerancesTestCase:
    description: str
    raw: object
    expected_result: RowDiffTolerances


@dataclass(frozen=True)
class ParseRowDiffTolerancesErrorTestCase:
    description: str
    raw: object
    expected_error_fragment: str
    expected_code: str


@dataclass(frozen=True)
class ResolveBoundedCursorsTestCase:
    description: str
    config_values: dict[str, object]
    bounded: str | None
    expected_cursor_column: str | None
    expected_start_cursor: CursorValue | None
    expected_end_cursor_kind: str | None
    expected_fallback: bool


@dataclass(frozen=True)
class ResolveBoundedCursorsErrorTestCase:
    description: str
    config_values: dict[str, object]
    bounded: str | None
    expected_error_fragment: str
    expected_code: str


@dataclass(frozen=True)
class WrongTypedBoundedCursorTestCase:
    description: str
    config_values: dict[str, object]
    bounded: str
    expected_key: str
    expected_type: str
