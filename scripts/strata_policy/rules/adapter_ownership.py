"""Repository-specific adapter implementation ownership rules."""

from __future__ import annotations

import ast

from strata import Family, Fault, RuleContext, rule

from scripts.strata_policy._helpers.adapter_contracts import (
    abstract_adapter_method_names,
    adapter_contract_class_names,
)
from scripts.strata_policy.constants import BASE_ADAPTER_CLASS_NAME, SUPER_CALL_NAME


@rule(
    code="XSB037",
    family=Family.CUSTOM,
    slug="adapter-method-alias",
    message="first-class adapter methods must not alias BaseAdapter implementations",
    remediation="Copy the implementation into the owning adapter class so overrides are explicit.",
)
def adapter_method_alias(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    checked_class_names: frozenset[str] = adapter_contract_class_names(
        path_parts=ctx.repo_relative_parts(),
        module=module,
        ctx=ctx,
    )
    faults: list[Fault] = []
    class_node: ast.ClassDef
    for class_node in (node for node in module.body if isinstance(node, ast.ClassDef)):
        if class_node.name not in checked_class_names:
            continue
        child: ast.stmt
        for child in class_node.body:
            value: ast.expr | None = None
            if isinstance(child, ast.Assign):
                value = child.value
            elif isinstance(child, ast.AnnAssign):
                value = child.value
            if (
                isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id == BASE_ADAPTER_CLASS_NAME
            ):
                faults.append(ctx.fault(node=child))
    return faults


@rule(
    code="XSB038",
    family=Family.CUSTOM,
    slug="adapter-super-delegation",
    message="first-class adapter contract methods must not delegate to super()",
    remediation="Own the complete contract method implementation in the adapter class.",
)
def adapter_super_delegation(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    checked_class_names: frozenset[str] = adapter_contract_class_names(
        path_parts=ctx.repo_relative_parts(),
        module=module,
        ctx=ctx,
    )
    if not checked_class_names:
        return []
    contract_methods: frozenset[str] = abstract_adapter_method_names(ctx=ctx)
    faults: list[Fault] = []
    class_node: ast.ClassDef
    for class_node in (node for node in module.body if isinstance(node, ast.ClassDef)):
        if class_node.name not in checked_class_names:
            continue
        child: ast.stmt
        for child in class_node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if child.name not in contract_methods:
                continue
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == SUPER_CALL_NAME
                for node in ast.walk(child)
            ):
                faults.append(ctx.fault(node=child))
    return faults
