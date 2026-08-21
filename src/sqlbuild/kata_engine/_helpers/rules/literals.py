"""Built-in literal and declaration hygiene rules."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration
from sqlbuild.kata_engine._helpers.sql.ast import kind
from sqlbuild.kata_engine._helpers.sql.decisions import (
    comparison_signature,
    decision_comparison_signatures,
)
from sqlbuild.kata_engine.constants import (
    AST_COLUMN_KIND,
    AST_LITERAL_KIND,
    CANONICAL_NUMERIC_LITERALS,
    DECLARATION_DOMAIN_PART_COUNT,
)
from sqlbuild.kata_engine.models import KataFault, KataRule
from sqlbuild.kata_engine.types import RuleContext

_COMPARISONS: frozenset[str] = frozenset({"eq", "neq", "gt", "gte", "lt", "lte"})


def _rule(
    *,
    code: str,
    slug: str,
    message: str,
    remediation: str,
    check: Any,
    project_wide: bool = False,
) -> KataRule:
    return KataRule(
        code=code,
        family="hygiene",
        slug=slug,
        message=message,
        remediation=remediation,
        check=check,
        project_wide=project_wide,
    )


def unnamed_enum_strings(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    enum_columns: frozenset[str] = frozenset(model.enum_columns)
    decisions: frozenset[str] = decision_comparison_signatures(ast=ctx.ast)
    faults: list[KataFault] = []
    for comparison in ctx.ast.walk():
        if (
            kind(comparison) not in _COMPARISONS
            or comparison_signature(node=comparison) not in decisions
        ):
            continue
        column_names: frozenset[str] = frozenset(
            str(getattr(node, "name", ""))
            for node in comparison.walk()
            if kind(node) == AST_COLUMN_KIND
        )
        bare_string: bool = any(
            kind(node) == AST_LITERAL_KIND
            and bool(getattr(node, "is_string", False))
            and node.sql() in ctx.source
            for node in comparison.walk()
        )
        if column_names & enum_columns and bare_string:
            faults.append(ctx.fault(node=comparison))
    return faults


def magic_numeric_comparison(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    decisions: frozenset[str] = decision_comparison_signatures(ast=ctx.ast)
    faults: list[KataFault] = []
    for comparison in ctx.ast.walk():
        if (
            kind(comparison) not in _COMPARISONS
            or comparison_signature(node=comparison) not in decisions
        ):
            continue
        values: tuple[str, ...] = tuple(
            str(getattr(node, "name", ""))
            for node in comparison.walk()
            if kind(node) == AST_LITERAL_KIND
            and bool(getattr(node, "is_number", False))
            and node.sql() in ctx.source
        )
        if any(value not in CANONICAL_NUMERIC_LITERALS for value in values):
            faults.append(ctx.fault(node=comparison))
    return faults


def duplicate_enums(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    if not ctx.is_project_anchor:
        return []
    signatures: dict[tuple[tuple[str, str], ...], EnumDeclaration] = {}
    faults: list[KataFault] = []
    for declaration in ctx.all_enum_declarations:
        signature: tuple[tuple[str, str], ...] = tuple(
            sorted((member.name, repr(member.value)) for member in declaration.members)
        )
        previous: EnumDeclaration | None = signatures.get(signature)
        if previous is not None:
            faults.append(
                ctx.fault_for(
                    path=declaration.relative_path,
                    message=f"enum {declaration.name!r} duplicates {previous.name!r}",
                )
            )
        signatures[signature] = declaration
    return faults


def declaration_domain_placement(*, model: CompiledModel, ctx: RuleContext) -> list[KataFault]:
    del model
    if not ctx.is_project_anchor:
        return []
    faults: list[KataFault] = []
    declarations: tuple[EnumDeclaration | ConstantDeclaration, ...] = (
        *ctx.public_enums,
        *ctx.public_constants,
    )
    for declaration in declarations:
        path_parts: tuple[str, ...] = declaration.relative_path.parts
        domain: str | None = (
            path_parts[1] if len(path_parts) >= DECLARATION_DOMAIN_PART_COUNT else None
        )
        if domain is not None and (
            not ctx.kata_config.domains or domain in ctx.kata_config.domains
        ):
            continue
        expected: str = "<domain>"
        if ctx.kata_config.domains:
            expected = "|".join(ctx.kata_config.domains)
        faults.append(
            ctx.fault_for(
                path=declaration.relative_path,
                message=f"public declaration {declaration.name!r} has no configured domain folder",
                remediation=(
                    f"Move this declaration under {path_parts[0]}/{expected}/ at this file path."
                ),
            )
        )
    return faults


def literal_rules() -> tuple[KataRule, ...]:
    """Return built-in literal-discipline rules."""

    return (
        _rule(
            code="KTH001",
            slug="named-enum-decisions",
            message="enum comparisons must use declared enum members",
            remediation=(
                'Replace this bare string with @enum("<enum>").<MEMBER> so the decision uses '
                "the declared domain."
            ),
            check=unnamed_enum_strings,
        ),
        _rule(
            code="KTH002",
            slug="named-numeric-decisions",
            message="non-canonical numeric comparisons must use constants",
            remediation=(
                'Declare the threshold as a CONSTANT and compare through @const("<name>"); '
                "only -1, 0, and 1 are self-explanatory."
            ),
            check=magic_numeric_comparison,
        ),
        _rule(
            code="KTH101",
            slug="duplicate-enums",
            message="identical enum domains must be consolidated",
            remediation=(
                "Keep one public enum declaration and replace the duplicate declaration's "
                "references with it."
            ),
            check=duplicate_enums,
            project_wide=True,
        ),
        _rule(
            code="KTH201",
            slug="declaration-domain-placement",
            message="public enum and constant files must live under a configured domain folder",
            remediation="Move this declaration beneath enums/<domain>/ or constants/<domain>/.",
            check=declaration_domain_placement,
            project_wide=True,
        ),
    )
