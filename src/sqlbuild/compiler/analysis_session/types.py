"""Native model analysis session row types."""

from __future__ import annotations

type ShapeRows = list[tuple[str, list[tuple[str, str]]]]
type ColumnRow = tuple[str, str | None, str]
type DiagnosticRow = tuple[str, str, int | None, int | None, int | None, int | None, str]
type LineageItem = tuple[str, int, int, list[tuple[str, str, str]]]
type DeferredRow = tuple[int, bool, list[ColumnRow] | None, bool, bool, list[DiagnosticRow], bool]
type DeferralRow = tuple[
    str, int, str | None, ShapeRows, list[DiagnosticRow], list[LineageItem] | None
]
type StepRow = tuple[ShapeRows, list[DeferralRow], list[str]]
type OutcomeRow = tuple[
    bool,
    list[ColumnRow] | None,
    str,
    list[LineageItem],
    bool,
    bool,
    list[DiagnosticRow],
    bool,
    str,
]
type FamilyRow = tuple[str, str, str, str, str, str | None]
type ProofRow = tuple[
    bool, list[ColumnRow], list[tuple[str, str | None]], list[str], str | None, bool
]
type ContractRow = tuple[str, ProofRow | None]
type FinishRow = tuple[list[OutcomeRow], ShapeRows, list[str], list[ContractRow]]
