"""Repository-specific orchestration dataflow rules."""

from __future__ import annotations

import ast

from strata import Family, Fault, RuleContext, rule

from scripts.strata_policy._helpers.ast_checks import (
    discarded_call_is_allowed,
    function_parameter_names,
    parameter_mutated_by_node,
)
from scripts.strata_policy._helpers.metadata_calls import (
    metadata_bearing_helper_names,
    metadata_call_label,
)
from scripts.strata_policy._helpers.path_checks import is_adapter_implementation_path
from scripts.strata_policy.constants import (
    ALLOWED_METADATA_LOOP_PATHS,
    ALLOWED_PARAMETER_MUTATION_COMMENT,
    COMPILER_EXECUTOR_DOMAIN_NAMES,
    HELPERS_PACKAGE_NAME,
    INIT_MODULE_NAME,
    NESTED_HELPER_MODULE_MIN_PARTS,
    ROOT_SCOPE_NAME,
    RUNTIME_ROOT_PARTS,
)


@rule(
    code="XSB051",
    family=Family.CUSTOM,
    slug="metadata-query-loop",
    message="warehouse metadata calls must not run once per loop iteration",
    remediation="Gather metadata once into a relation lookup or WarehouseSnapshot before looping.",
)
def metadata_query_loop(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    if ctx.scope() != ROOT_SCOPE_NAME:
        return []
    path: str = "/".join(ctx.repo_relative_parts())
    if path in ALLOWED_METADATA_LOOP_PATHS or is_adapter_implementation_path(path=path):
        return []
    bearing_method_names, bearing_function_names = metadata_bearing_helper_names(module=module)
    faults: list[Fault] = []
    node: ast.AST
    for node in ctx.nodes(ast.Call):
        if not isinstance(node, ast.Call) or not ctx.inside_loop(node):
            continue
        label: str | None = metadata_call_label(
            node=node,
            bearing_method_names=bearing_method_names,
            bearing_function_names=bearing_function_names,
        )
        if label is not None:
            faults.append(
                ctx.fault(
                    node=node,
                    message=(
                        f"'{label}' reaches a warehouse metadata call inside a loop and risks "
                        "N+1 warehouse queries"
                    ),
                )
            )
    return faults


@rule(
    code="XSB066",
    family=Family.CUSTOM,
    slug="main-discarded-call",
    message="main orchestrators must consume bare phase call results",
    remediation="Assign, return, or explicitly discard the result with _ = call(...).",
)
def main_discarded_call(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    if ctx.scope() != ROOT_SCOPE_NAME:
        return []
    if not ctx.is_main_module() or ctx.path.name == INIT_MODULE_NAME:
        return []
    faults: list[Fault] = []
    function_node: ast.AST
    for function_node in ctx.top_level_functions(module):
        node: ast.AST
        for node in ast.walk(function_node):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            if not discarded_call_is_allowed(node.value):
                faults.append(ctx.fault(node=node))
    return faults


@rule(
    code="XSB067",
    family=Family.CUSTOM,
    slug="phase-parameter-mutation",
    message="compiler and executor phase helpers must not mutate input parameters",
    remediation=(
        "Return updated values, or mark a deliberate builder with # sc: allow-param-mutation."
    ),
)
def phase_parameter_mutation(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    parts: tuple[str, ...] = ctx.repo_relative_parts()
    if (
        len(parts) < NESTED_HELPER_MODULE_MIN_PARTS
        or parts[:2] != RUNTIME_ROOT_PARTS
        or parts[2] not in COMPILER_EXECUTOR_DOMAIN_NAMES
        or HELPERS_PACKAGE_NAME not in parts[3:-1]
    ):
        return []
    faults: list[Fault] = []
    function_node: ast.AST
    for function_node in ctx.nodes(ast.FunctionDef) + ctx.nodes(ast.AsyncFunctionDef):
        if not isinstance(function_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        parameter_names: frozenset[str] = function_parameter_names(function_node)
        node: ast.AST
        for node in ast.walk(function_node):
            mutated_name: str | None = parameter_mutated_by_node(
                node=node,
                parameter_names=parameter_names,
            )
            if mutated_name is None:
                continue
            line_number: int = getattr(node, "lineno", function_node.lineno)
            if ALLOWED_PARAMETER_MUTATION_COMMENT in ctx.text.line(line_number):
                continue
            faults.append(
                ctx.fault(
                    node=node,
                    message=f"'{mutated_name}' is a parameter and is mutated here",
                )
            )
    return faults
