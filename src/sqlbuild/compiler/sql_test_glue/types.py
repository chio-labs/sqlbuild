"""Row shapes the native SQL-test glue returns."""

from __future__ import annotations

from typing import Literal

type CtePairRow = tuple[str, str]
type NativeChainStepRow = tuple[
    str,
    str,
    str | None,
    list[CtePairRow],
    str | None,
    list[str] | None,
    list[CtePairRow],
]
type NativeAssertionStepRow = tuple[str, str, list[CtePairRow], str | None]
type NativePlanWarningRow = tuple[str | None, str, str]
type NativeSqlTestPlanRow = tuple[
    str | None,
    list[NativeChainStepRow],
    list[NativeAssertionStepRow],
    list[str],
    list[NativePlanWarningRow],
    list[str],
]
type SqlTestAssemblyFailureKind = Literal["input", "internal", "decimal_overflow"]
