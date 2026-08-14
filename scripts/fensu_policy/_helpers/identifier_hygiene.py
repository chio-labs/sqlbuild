"""Warehouse identifier normalization predicates for SQLBuild custom rules."""

from __future__ import annotations

import ast

from fensu import DataclassFact, RuleContext

from scripts.fensu_policy.constants import (
    IDENTIFIER_NORMALIZATION_METHOD_NAME,
    RELATION_IDENTITY_KEY_FIELD_NAMES,
)


def is_relation_identity_key(*, ctx: RuleContext, declaration: DataclassFact) -> bool:
    """Return whether a dataclass exists solely as a warehouse relation identity."""

    if not declaration.frozen:
        return False
    if declaration.field_names != RELATION_IDENTITY_KEY_FIELD_NAMES:
        return False
    return not declares_defaulted_fields(ctx=ctx, class_name=declaration.name)


def declares_defaulted_fields(*, ctx: RuleContext, class_name: str) -> bool:
    """Return whether a class declares any annotated field with a default value."""

    definition: ast.AST
    for definition in ctx.nodes(ast.ClassDef):
        if not isinstance(definition, ast.ClassDef) or definition.name != class_name:
            continue
        return any(
            isinstance(member, ast.AnnAssign) and member.value is not None
            for member in definition.body
        )
    return False


def declares_identifier_normalization(*, ctx: RuleContext, class_name: str) -> bool:
    """Return whether a class declares an identifier normalization hook."""

    definition: ast.AST
    for definition in ctx.nodes(ast.ClassDef):
        if not isinstance(definition, ast.ClassDef) or definition.name != class_name:
            continue
        return any(
            isinstance(member, ast.FunctionDef)
            and member.name == IDENTIFIER_NORMALIZATION_METHOD_NAME
            for member in definition.body
        )
    return False
