"""Built-in explicit-join rules."""

from __future__ import annotations

from typing import Any, cast

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.kata_engine._helpers.sql.ast import nodes, payload
from sqlbuild.kata_engine.constants import CANONICAL_ONE, CROSS_JOIN_KIND
from sqlbuild.kata_engine.models import KataFault, KataRule
from sqlbuild.kata_engine.types import RuleContext


def _rule(*, code: str, slug: str, message: str, remediation: str, check: Any) -> KataRule:
    return KataRule(
        code=code, family="joins", slug=slug, message=message, remediation=remediation, check=check
    )


def explicit_join_keys(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    faults: list[KataFault] = []
    for select in nodes(root=ctx.ast, wanted="select"):
        for join in _select_joins(select=select):
            join_kind: str = str(join.get("kind", "") or "").upper()
            if join_kind == CROSS_JOIN_KIND:
                continue
            on_clause: object = join.get("on")
            trivially_true: bool = _is_trivially_true(on_clause=on_clause)
            if (on_clause is None and not join.get("using")) or trivially_true:
                faults.append(ctx.fault(node=select))
    return faults


def _is_trivially_true(*, on_clause: object) -> bool:
    if not isinstance(on_clause, dict):
        return False
    mapping: dict[str, object] = cast(dict[str, object], on_clause)
    equality: object = mapping.get("eq")
    if not isinstance(equality, dict):
        return False
    equality_mapping: dict[str, object] = cast(dict[str, object], equality)
    values: list[str] = []
    for side in ("left", "right"):
        operand: object = equality_mapping.get(side)
        if not isinstance(operand, dict):
            return False
        literal: object = cast(dict[str, object], operand).get("literal")
        if not isinstance(literal, dict):
            return False
        value: object = cast(dict[str, object], literal).get("value")
        values.append(str(value))
    return values == [CANONICAL_ONE, CANONICAL_ONE]


def no_cross_join(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    faults: list[KataFault] = []
    for select in nodes(root=ctx.ast, wanted="select"):
        for join in _select_joins(select=select):
            join_kind: str = str(join.get("kind", "") or "").upper()
            if join_kind == CROSS_JOIN_KIND:
                faults.append(ctx.fault(node=select))
    return faults


def no_comma_join(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    faults: list[KataFault] = []
    for select in nodes(root=ctx.ast, wanted="select"):
        from_payload: object = payload(select).get("from")
        if not isinstance(from_payload, dict):
            continue
        expressions: object = cast(dict[str, object], from_payload).get("expressions")
        if isinstance(expressions, list) and len(expressions) > 1:
            faults.append(ctx.fault(node=select))
    return faults


def _select_joins(*, select: Any) -> tuple[dict[str, object], ...]:
    raw_joins: object = payload(select).get("joins")
    if not isinstance(raw_joins, list):
        return ()
    joins: list[dict[str, object]] = []
    for raw_join in raw_joins:
        if isinstance(raw_join, dict):
            joins.append(cast(dict[str, object], raw_join))
    return tuple(joins)


def join_rules() -> tuple[KataRule, ...]:
    """Return built-in join rules."""

    return (
        _rule(
            code="KTJ001",
            slug="no-comma-join",
            message="implicit comma joins are not permitted",
            remediation="Replace the comma join with an explicit JOIN ... ON <key> at this FROM.",
            check=no_comma_join,
        ),
        _rule(
            code="KTJ101",
            slug="explicit-join-key",
            message="non-cross joins must declare ON or USING",
            remediation="Add an explicit JOIN ... ON <key> or JOIN ... USING (<key>) condition.",
            check=explicit_join_keys,
        ),
        _rule(
            code="KTJ002",
            slug="no-cross-join",
            message="cross joins require an explicit project exception",
            remediation=(
                "Replace CROSS JOIN with an explicit keyed join, or add a reasoned exact "
                "exception when the Cartesian product is intentional."
            ),
            check=no_cross_join,
        ),
    )
