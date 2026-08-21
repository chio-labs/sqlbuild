"""Built-in contract-backed column naming rules."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.kata_engine.constants import BOOLEAN_TYPE, DATE_TYPE, TIMESTAMP_TYPE
from sqlbuild.kata_engine.models import KataFault, KataRule
from sqlbuild.kata_engine.types import RuleContext


def _rule(*, code: str, slug: str, message: str, remediation: str, check: Any) -> KataRule:
    return KataRule(
        code=code, family="naming", slug=slug, message=message, remediation=remediation, check=check
    )


def _columns(model: CompiledModel) -> tuple[tuple[str, str], ...]:
    if model.schema_entry is None:
        return ()
    return tuple(
        (column.name, column.type.upper()) for column in model.schema_entry.columns if column.type
    )


def boolean_names(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    return [
        ctx.path_fault(message=f"column {name!r} implies BOOLEAN but is typed {data_type}")
        for name, data_type in _columns(model)
        if name.startswith(("is_", "has_", "can_")) and data_type != BOOLEAN_TYPE
    ]


def timestamp_names(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    return [
        ctx.path_fault(message=f"column {name!r} implies a timestamp but is typed {data_type}")
        for name, data_type in _columns(model)
        if name.endswith(("_at", "_ts", "_timestamp")) and TIMESTAMP_TYPE not in data_type
    ]


def date_names(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    return [
        ctx.path_fault(message=f"column {name!r} implies DATE but is typed {data_type}")
        for name, data_type in _columns(model)
        if name.endswith("_date") and data_type != DATE_TYPE
    ]


def naming_rules() -> tuple[KataRule, ...]:
    """Return built-in naming-contract rules."""

    return (
        _rule(
            code="KTN001",
            slug="boolean-column-name",
            message="boolean column names must have BOOLEAN types",
            remediation=(
                "Declare this is_/has_/can_ column as BOOLEAN in columns (...), or rename it "
                "to match its actual type."
            ),
            check=boolean_names,
        ),
        _rule(
            code="KTN002",
            slug="timestamp-column-name",
            message="timestamp column names must have timestamp types",
            remediation=(
                "Declare this *_at/*_ts/*_timestamp column with a timestamp type in columns "
                "(...), or rename it."
            ),
            check=timestamp_names,
        ),
        _rule(
            code="KTN003",
            slug="date-column-name",
            message="date column names must have DATE types",
            remediation=(
                "Declare this *_date column as DATE in columns (...), or rename it to match its "
                "actual type."
            ),
            check=date_names,
        ),
    )
