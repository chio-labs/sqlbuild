"""Built-in SQL structure rules."""

from __future__ import annotations

import re
from fnmatch import fnmatch
from typing import Any, cast

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.kata_engine._helpers.sql.ast import cte_name, kind, nodes, payload, top_level_ctes
from sqlbuild.kata_engine._helpers.sql.model_name import parse_model_name
from sqlbuild.kata_engine._helpers.sql.passthrough import (
    is_dependency_import,
    is_plain_projection,
)
from sqlbuild.kata_engine.constants import (
    AST_SELECT_KIND,
    AST_STAR_KIND,
    FINAL_CTE_NAMES,
    MATERIALIZED_VIEW,
    SET_OPERATION_BY_NAME,
    SQL_BLOCK_COMMENT,
    SQL_LINE_COMMENT,
)
from sqlbuild.kata_engine.models import KataFault, KataRule, ModelNameParts
from sqlbuild.kata_engine.types import RuleContext

_REFERENCE_PATTERN: re.Pattern[str] = re.compile(r"__(?:ref|source)\s*\(", re.IGNORECASE)
_MEANINGLESS_CTE_PATTERN: re.Pattern[str] = re.compile(
    r"(?:[a-z]{1,2}\d*|(?:cte|tmp|temp|t|tbl|table|q|query|sub|subquery|step|s)\d*|final\d+|finalfinal)"
)
_MEANINGLESS_CTE_NAMES: frozenset[str] = frozenset(
    {
        "data",
        "result",
        "results",
        "output",
        "rows",
        "records",
        "stuff",
        "things",
        "working",
        "scratch",
        "misc",
        "temp_table",
        "tmp_table",
    }
)
_MIXED_STAR_REMEDIATION: str = (
    "SELECT *, a, b mixes a passthrough star with derived columns. The * exemption permits a "
    "lone SELECT * only. Move a and b into an earlier CTE so they are computed upstream, leaving "
    "the final select a pure SELECT *. If you need those columns in the output, drop the * "
    "exemption and enumerate every column explicitly."
)
_CTE_OPEN_PATTERN: re.Pattern[str] = re.compile(r"\b[A-Za-z_][\w]*\s+AS\s*\(\s*$", re.IGNORECASE)


def _rule(*, code: str, slug: str, message: str, remediation: str, check: Any) -> KataRule:
    return KataRule(
        code=code,
        family="structure",
        slug=slug,
        message=message,
        remediation=remediation,
        check=check,
    )


def cte_only(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    ctes: tuple[Any, ...] = top_level_ctes(ctx.ast)
    if not ctes:
        return [ctx.path_fault()]
    data: dict[str, object] = payload(ctx.ast)
    if data.get("joins") or data.get("where_clause") or data.get("group_by"):
        return [ctx.path_fault()]
    return []


def terminal_select(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    ctes: tuple[Any, ...] = top_level_ctes(ctx.ast)
    if not ctes:
        return []
    data: dict[str, object] = payload(ctx.ast)
    from_payload: object = data.get("from")
    terminal_sql: str = str(from_payload)
    if cte_name(ctes[-1]) not in terminal_sql:
        return [ctx.path_fault(message="terminal SELECT must read from the final top-level CTE")]
    if not is_plain_projection(select=ctx.ast, allow_star=True):
        return [ctx.path_fault(message="terminal SELECT contains logic outside the final CTE")]
    return []


def comment_discipline(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    faults: list[KataFault] = []
    previous_code: str = ""
    cte_head_comment_seen: bool = False
    for line_number, line in enumerate(model.query_sql.splitlines(), start=1):
        stripped: str = line.strip()
        is_comment: bool = stripped.startswith(SQL_LINE_COMMENT) or stripped.startswith(
            SQL_BLOCK_COMMENT
        )
        if is_comment:
            at_cte_head: bool = _CTE_OPEN_PATTERN.search(previous_code) is not None
            if not at_cte_head or cte_head_comment_seen:
                faults.append(ctx.fault_at(line=line_number, column=1))
            if at_cte_head:
                cte_head_comment_seen = True
            continue
        if SQL_LINE_COMMENT in line or SQL_BLOCK_COMMENT in line:
            faults.append(ctx.fault_at(line=line_number, column=1))
        if stripped:
            previous_code = stripped
            cte_head_comment_seen = False
    return faults


def import_ctes(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    faults: list[KataFault] = []
    imported_references: list[str] = []
    logical_cte_seen: bool = False
    for cte in top_level_ctes(ctx.ast):
        body_node: Any = cte[1]
        body: str = body_node.sql()
        references: list[str] = _dependency_calls(source=body)
        if not references:
            logical_cte_seen = True
            continue
        if len(references) > 1:
            faults.append(
                ctx.fault(
                    node=body_node,
                    message=f"import CTE {cte_name(cte)!r} reads multiple dependencies",
                )
            )
        if len(references) == 1:
            imported_references.extend(references)
            if logical_cte_seen:
                faults.append(
                    ctx.fault(
                        node=body_node,
                        message=f"import CTE {cte_name(cte)!r} appears after logical CTEs",
                    )
                )
            if not _is_import_shape(node=body_node):
                faults.append(
                    ctx.fault(
                        node=body_node,
                        message=f"import CTE {cte_name(cte)!r} contains transformation logic",
                    )
                )
    authored_references: list[str] = _dependency_calls(source=model.query_sql)
    has_duplicate_calls: bool = len(set(authored_references)) != len(authored_references)
    if has_duplicate_calls or sorted(authored_references) != sorted(imported_references):
        faults.append(
            ctx.path_fault(
                message="each __ref/__source must appear once in its own top-level import CTE"
            )
        )
    return faults


def _is_import_shape(*, node: Any) -> bool:
    return is_dependency_import(node=node)


def _dependency_calls(*, source: str) -> list[str]:
    calls: list[str] = []
    for match in _REFERENCE_PATTERN.finditer(source):
        tail: str = source[match.start() :]
        closing: int = tail.find(")")
        call: str = tail[: closing + 1] if closing >= 0 else tail
        calls.append(call.lower())
    return calls


def select_star(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    allowed: bool = False
    for entry in ctx.kata_config.select_star_allow:
        if any(fnmatch(model.relative_path.as_posix(), pattern) for pattern in entry.paths):
            allowed = True
            break
    import_names: frozenset[str] = frozenset(
        cte_name(cte) for cte in top_level_ctes(ctx.ast) if is_dependency_import(node=cte[1])
    )
    faults: list[KataFault] = []
    for star in nodes(root=ctx.ast, wanted=AST_STAR_KIND):
        owner_name: str | None = None
        for cte in top_level_ctes(ctx.ast):
            if any(id(node) == id(star) for node in cte[1].walk()):
                owner_name = cte_name(cte)
                break
        if owner_name in import_names:
            continue
        owner: Any = ctx.ast
        for cte in top_level_ctes(ctx.ast):
            if any(id(node) == id(star) for node in cte[1].walk()):
                owner = cte[1]
                break
        expressions: tuple[Any, ...] = tuple(owner.expressions)
        if allowed and len(expressions) == 1 and kind(expressions[0]) == AST_STAR_KIND:
            continue
        if allowed and len(expressions) > 1:
            faults.append(ctx.fault(node=star, remediation=_MIXED_STAR_REMEDIATION))
            continue
        faults.append(ctx.fault(node=star))
    return faults


def nested_ctes(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    top_with_count: int = 1 if top_level_ctes(ctx.ast) else 0
    nested_with_count: int = sum(
        1 for select in nodes(root=ctx.ast, wanted=AST_SELECT_KIND) if payload(select).get("with")
    )
    return [ctx.path_fault()] if nested_with_count > top_with_count else []


def recursive_ctes(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    data: dict[str, object] = payload(ctx.ast)
    with_payload: object = data.get("with")
    if (
        isinstance(with_payload, dict)
        and cast(dict[str, object], with_payload).get("recursive") is True
    ):
        return [ctx.path_fault()]
    return []


def view_marker(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    parts: ModelNameParts | None = parse_model_name(model.name)
    if parts is None:
        return []
    is_view: bool = model.config.values.get("materialized") == MATERIALIZED_VIEW
    return [] if parts.is_view == is_view else [ctx.path_fault()]


def positional_set_star(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    faults: list[KataFault] = []
    for union in (
        *nodes(root=ctx.ast, wanted="union"),
        *nodes(root=ctx.ast, wanted="except"),
        *nodes(root=ctx.ast, wanted="intersect"),
    ):
        sql: str = union.sql().upper()
        if SET_OPERATION_BY_NAME not in sql and any(
            kind(child) == AST_STAR_KIND for child in union.walk()
        ):
            faults.append(ctx.fault(node=union))
    return faults


def meaningless_cte_name(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    faults: list[KataFault] = []
    for cte in top_level_ctes(ctx.ast):
        name: str = cte_name(cte).lower()
        whitelist: frozenset[str] = frozenset(
            (*FINAL_CTE_NAMES, *ctx.kata_config.cte_name_whitelist)
        )
        denylist: frozenset[str] = frozenset(
            (*_MEANINGLESS_CTE_NAMES, *ctx.kata_config.cte_name_denylist)
        )
        if name in whitelist or name.endswith("_base"):
            continue
        if name in denylist or _MEANINGLESS_CTE_PATTERN.fullmatch(name):
            faults.append(ctx.fault(node=cte[1], message=f"CTE {name!r} has a meaningless name"))
    return faults


def structure_rules() -> tuple[KataRule, ...]:
    """Return built-in structure rules."""

    return (
        _rule(
            code="KTS000",
            slug="cte-comment-discipline",
            message="standalone SQL comments belong only on the first inner line of a CTE",
            remediation=(
                "Move this comment to the first inner line of the CTE it explains, or move "
                "model-level rationale into the MODEL description."
            ),
            check=comment_discipline,
        ),
        _rule(
            code="KTS001",
            slug="cte-only-body",
            message="model SQL must keep transformation logic in top-level CTEs",
            remediation=(
                "Move transformation logic into named top-level CTEs before the terminal SELECT."
            ),
            check=cte_only,
        ),
        _rule(
            code="KTS002",
            slug="single-terminal-select",
            message="the terminal SELECT must read from the final top-level CTE",
            remediation="Name the final logical CTE and leave one terminal SELECT from that CTE.",
            check=terminal_select,
        ),
        _rule(
            code="KTS101",
            slug="dependency-import-ctes",
            message="dependencies must be isolated in import CTEs",
            remediation=(
                "Move each __ref(...) or __source(...) into one named top-level import CTE and "
                "reference that CTE from later logic."
            ),
            check=import_ctes,
        ),
        _rule(
            code="KTS201",
            slug="select-star-discipline",
            message="SELECT * is allowed only inside dependency import CTEs",
            remediation=(
                "Enumerate output columns in this logical CTE or terminal SELECT; keep * only "
                "in a dependency import CTE."
            ),
            check=select_star,
        ),
        _rule(
            code="KTS202",
            slug="set-operation-star",
            message="positional set operations must not use star branches",
            remediation=(
                "Enumerate matching columns in every branch or use a supported BY NAME set "
                "operation."
            ),
            check=positional_set_star,
        ),
        _rule(
            code="KTS301",
            slug="nested-cte",
            message="CTEs must be top-level",
            remediation="Hoist this nested CTE into the model's top-level WITH list.",
            check=nested_ctes,
        ),
        _rule(
            code="KTS302",
            slug="recursive-cte",
            message="recursive CTEs are not permitted",
            remediation=(
                "Replace the recursive CTE with an explicit upstream model or a bounded "
                "non-recursive shape."
            ),
            check=recursive_ctes,
        ),
        _rule(
            code="KTS401",
            slug="view-marker",
            message="view materialization and model v marker must agree",
            remediation=(
                "Use stg_v/int_v/mart_v for a view, or change the materialization to match the "
                "non-view layer name."
            ),
            check=view_marker,
        ),
        _rule(
            code="KTS501",
            slug="descriptive-cte-name",
            message="CTE names must describe their contents",
            remediation=(
                "Name this CTE for what it holds, such as filtered_orders or top_two_finishers."
            ),
            check=meaningless_cte_name,
        ),
    )
