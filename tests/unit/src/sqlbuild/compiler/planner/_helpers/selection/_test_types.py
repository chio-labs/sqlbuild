from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.planner.models import SqlTestSelection


@dataclass(frozen=True)
class UnitTestSelectorSplitTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_select: tuple[str, ...]
    expected_exclude: tuple[str, ...]
    expected_selection: SqlTestSelection


@dataclass(frozen=True)
class UnitTestSelectorErrorTestCase:
    description: str
    select: tuple[str, ...]
    accepts_unit_tests: bool
    expected_code: str
    expected_message: str
    expected_help: str | None
