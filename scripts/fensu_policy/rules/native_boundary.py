"""Rules keeping the native bindings crate from calling back into Python outside its edges."""

from __future__ import annotations

import ast

from fensu import AnalyzerId, Family, Fault, File, RuleContext, rule

from scripts.fensu_policy._helpers.native_crossings import (
    budgeted_faults,
    budgets_by_path,
    crossing_lines,
    python_field_lines,
)
from scripts.fensu_policy._helpers.native_patches import native_patch_lines
from scripts.fensu_policy.constants import (
    NATIVE_EDGE_PATHS,
    NATIVE_PENDING_BUDGETS,
    NATIVE_TEST_PATCH_BUDGETS,
    NATIVE_TEST_PATH_PREFIX,
)


@rule(
    code="XSB072",
    family=Family.CUSTOM,
    slug="native-python-crossing",
    message="native bindings must not call back into Python outside the configured edges",
    remediation=(
        "Read native records with records::fields::field, build them with records::construct, "
        "call Rust functions directly, or route a real edge through bindings/_helpers/native_host."
    ),
    analyzers=(AnalyzerId.RUST,),
    options=(NATIVE_EDGE_PATHS, NATIVE_PENDING_BUDGETS),
)
def native_python_crossing(*, file: File, ctx: RuleContext) -> list[Fault]:
    del file
    return budgeted_faults(ctx=ctx, lines=crossing_lines, what="Python crossings")


@rule(
    code="XSB073",
    family=Family.CUSTOM,
    slug="native-python-storage",
    message="native bindings must not store Python objects outside the configured edges",
    remediation=(
        "Store Rust values or typed native records; keep Python objects only in "
        "bindings/_helpers/native_host for user values, adapters, hooks and streams."
    ),
    analyzers=(AnalyzerId.RUST,),
    options=(NATIVE_EDGE_PATHS, NATIVE_PENDING_BUDGETS),
)
def native_python_storage(*, file: File, ctx: RuleContext) -> list[Fault]:
    del file
    return budgeted_faults(ctx=ctx, lines=python_field_lines, what="Python-typed fields")


@rule(
    code="XSB074",
    family=Family.CUSTOM,
    slug="native-module-test-patch",
    message="tests must not replace attributes of sqlbuild._native",
    remediation=(
        "Assert observable behaviour or native work counters instead; native code calls its own "
        "functions directly, so a patched module attribute is not seen."
    ),
    options=(NATIVE_TEST_PATCH_BUDGETS,),
)
def native_module_test_patch(*, module: object, ctx: RuleContext) -> list[Fault]:
    path: str = "/".join(ctx.repo_relative_parts())
    if not path.startswith(NATIVE_TEST_PATH_PREFIX):
        return []
    tree: ast.Module = module if isinstance(module, ast.Module) else ast.parse(ctx.text.source)
    found: list[int] = native_patch_lines(tree=tree)
    budget: int = budgets_by_path(entries=ctx.option(NATIVE_TEST_PATCH_BUDGETS)).get(path, 0)
    if len(found) == budget:
        return []
    if len(found) < budget:
        return [
            ctx.fault_for(
                path=ctx.path,
                line=1,
                column=0,
                message=(
                    f"{len(found)} native patches, below the pending budget of {budget}; lower it"
                ),
            )
        ]
    return [ctx.fault_for(path=ctx.path, line=line, column=0) for line in found[budget:]]
