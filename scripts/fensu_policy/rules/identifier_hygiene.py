"""Repository-specific warehouse identifier normalization rules."""

from __future__ import annotations

import ast

from fensu import DataclassFact, Family, Fault, RuleContext, rule

from scripts.fensu_policy._helpers.identifier_hygiene import (
    declares_identifier_normalization,
    is_relation_identity_key,
)
from scripts.fensu_policy.constants import (
    IDENTIFIER_NORMALIZATION_ALLOWED_PREFIXES,
    POLICY_EVALUATION_SCOPES,
)


@rule(
    code="XSB068",
    family=Family.CUSTOM,
    slug="relation-identity-key-must-fold",
    message="relation identity keys must fold identifier case on construction",
    remediation=(
        "Add a __post_init__ that lowercases database, schema, and name. Warehouse "
        "identifiers are read lowercase while config identifiers are kept verbatim, so an "
        "unfolded identity key silently never compares equal."
    ),
)
def relation_identity_key_must_fold(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() not in POLICY_EVALUATION_SCOPES:
        return []
    path: str = "/".join(ctx.repo_relative_parts())
    if path.startswith(IDENTIFIER_NORMALIZATION_ALLOWED_PREFIXES):
        return []
    faults: list[Fault] = []
    declaration: DataclassFact
    for declaration in ctx.facts.dataclasses():
        if not is_relation_identity_key(ctx=ctx, declaration=declaration):
            continue
        if declares_identifier_normalization(ctx=ctx, class_name=declaration.name):
            continue
        faults.append(ctx.fault_at(location=declaration.location))
    return faults
