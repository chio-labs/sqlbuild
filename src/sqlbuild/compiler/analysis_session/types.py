"""Native model analysis session row types."""

from __future__ import annotations

from typing import Literal

type ColumnRow = tuple[str, str | None, str]
type DiagnosticRow = tuple[str, str, int | None, int | None, int | None, int | None, str]
type ProofRow = tuple[
    bool, list[ColumnRow], list[tuple[str, str | None]], list[str], str | None, bool
]

type QueryColumnsMode = Literal["batch", "reanalysis", "parse", "legacy"]
