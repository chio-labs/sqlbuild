"""Repository-specific canonical operation ownership rules."""

from __future__ import annotations

import ast

from strata import Family, Fault, RuleContext, rule

from scripts.strata_policy._helpers.ast_checks import base_name, call_base_name
from scripts.strata_policy.constants import (
    ALLOWED_DBT_REF_SCAN_PATHS,
    ALLOWED_MACRO_LOAD_PATHS,
    ALLOWED_SELECTOR_PARSE_PATH,
    ALLOWED_SOURCE_FRESHNESS_INSERT_PREFIXES,
    DBT_INTEGRATION_PATH_PREFIX,
    DBT_REF_ATTRIBUTE_NAME,
    GRAPH_KEY_CLASS_NAMES,
    INSERT_SQL_PREFIX,
    LOAD_PROJECT_MACROS_NAME,
    PLANNER_PATH_PREFIX,
    POLICY_EVALUATION_SCOPES,
    PUBLIC_COLOR_ENTRY_PARTS,
    ROOT_SCOPE_NAME,
    SELECTOR_MARKER,
    SELECTOR_STRING_METHOD_NAMES,
    SOURCE_FRESHNESS_MARKERS,
    SOURCE_FRESHNESS_SINGULAR_WRITER,
    SQL_REFERENCE_KIND_CLASS_NAME,
)


@rule(
    code="XSB041",
    family=Family.CUSTOM,
    slug="color-capability-entry",
    message="color capability imports must use the presentation main entry",
    remediation="Import supports_color from sqlbuild.presentation.main.supports_color.",
)
def color_capability_entry(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    if ctx.repo_relative_parts() == PUBLIC_COLOR_ENTRY_PARTS:
        return []
    raw_module: str = "sqlbuild.presentation._helpers.terminal_capabilities"
    faults: list[Fault] = []
    node: ast.AST
    for node in ctx.nodes(ast.ImportFrom):
        if isinstance(node, ast.ImportFrom) and node.module == raw_module:
            faults.append(ctx.fault(node=node))
    for node in ctx.nodes(ast.Import):
        if isinstance(node, ast.Import) and any(alias.name == raw_module for alias in node.names):
            faults.append(ctx.fault(node=node))
    return faults


@rule(
    code="XSB052",
    family=Family.CUSTOM,
    slug="dbt-reference-resolution",
    message="dbt references must be identified by the centralized manifest resolver",
    remediation="Resolve __dbt_ref through integrations/dbt/_helpers/manifest/sqlbuild_refs.py.",
)
def dbt_reference_resolution(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    path: str = "/".join(ctx.repo_relative_parts())
    if DBT_INTEGRATION_PATH_PREFIX not in path or path in ALLOWED_DBT_REF_SCAN_PATHS:
        return []
    faults: list[Fault] = []
    node: ast.AST
    for node in ctx.nodes(ast.Compare):
        if not isinstance(node, ast.Compare):
            continue
        expressions: tuple[ast.expr, ...] = (node.left, *node.comparators)
        if any(
            isinstance(expression, ast.Attribute)
            and expression.attr == DBT_REF_ATTRIBUTE_NAME
            and base_name(expression.value) == SQL_REFERENCE_KIND_CLASS_NAME
            for expression in expressions
        ):
            faults.append(ctx.fault(node=node))
    return faults


@rule(
    code="XSB053",
    family=Family.CUSTOM,
    slug="dbt-graph-projection",
    message="dbt graph keys must be constructed by the centralized projection helper",
    remediation="Use integrations/dbt/_helpers/planning/graph_projection.py.",
)
def dbt_graph_projection(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    path: str = "/".join(ctx.repo_relative_parts())
    if DBT_INTEGRATION_PATH_PREFIX not in path or path.endswith(
        "src/sqlbuild/integrations/dbt/_helpers/planning/graph_projection.py"
    ):
        return []
    return [
        ctx.fault(node=node)
        for node in ctx.nodes(ast.Call)
        if isinstance(node, ast.Call) and call_base_name(node) in GRAPH_KEY_CLASS_NAMES
    ]


@rule(
    code="XSB054",
    family=Family.CUSTOM,
    slug="selector-marker-parsing",
    message="selector + markers must be parsed by split_selector_expansion",
    remediation="Use compiler.planner.main.selection.selector_expansion.split_selector_expansion.",
)
def selector_marker_parsing(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    path: str = "/".join(ctx.repo_relative_parts())
    if (
        not (DBT_INTEGRATION_PATH_PREFIX in path or PLANNER_PATH_PREFIX in path)
        or path == ALLOWED_SELECTOR_PARSE_PATH
    ):
        return []
    faults: list[Fault] = []
    node: ast.AST
    for node in ctx.nodes(ast.Call):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in SELECTOR_STRING_METHOD_NAMES or not node.args:
            continue
        first_argument: ast.expr = node.args[0]
        if isinstance(first_argument, ast.Constant) and first_argument.value == SELECTOR_MARKER:
            faults.append(ctx.fault(node=node))
    return faults


@rule(
    code="XSB057",
    family=Family.CUSTOM,
    slug="source-freshness-batch-write",
    message="source freshness state must be written in batches",
    remediation="Use write_source_freshness_records() instead of the singular writer.",
)
def source_freshness_batch_write(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    if ctx.scope() not in POLICY_EVALUATION_SCOPES:
        return []
    faults: list[Fault] = []
    node: ast.AST
    for node in ctx.nodes(ast.ImportFrom):
        if isinstance(node, ast.ImportFrom) and any(
            alias.name == SOURCE_FRESHNESS_SINGULAR_WRITER for alias in node.names
        ):
            faults.append(ctx.fault(node=node))
    for node in ctx.nodes(ast.Call):
        if isinstance(node, ast.Call) and ctx.call_name(node) == SOURCE_FRESHNESS_SINGULAR_WRITER:
            faults.append(ctx.fault(node=node))
    return faults


@rule(
    code="XSB058",
    family=Family.CUSTOM,
    slug="source-freshness-sql-ownership",
    message="source freshness INSERT SQL must be rendered by adapters",
    remediation="Move source freshness INSERT rendering to the adapter contract.",
)
def source_freshness_sql_ownership(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    if ctx.scope() not in POLICY_EVALUATION_SCOPES:
        return []
    path: str = "/".join(ctx.repo_relative_parts())
    if path.startswith(ALLOWED_SOURCE_FRESHNESS_INSERT_PREFIXES):
        return []
    if all(marker not in ctx.text.source for marker in SOURCE_FRESHNESS_MARKERS):
        return []
    return [
        ctx.fault_for(path=ctx.path, line=line_number, column=0)
        for line_number, line in enumerate(ctx.text.source.splitlines(), start=1)
        if INSERT_SQL_PREFIX in line
    ]


@rule(
    code="XSB062",
    family=Family.CUSTOM,
    slug="single-macro-load-site",
    message="project macros must be loaded once in build_compile_inputs",
    remediation="Pass loaded_macros down instead of calling load_project_macros again.",
)
def single_macro_load_site(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    if ctx.scope() != ROOT_SCOPE_NAME:
        return []
    path: str = "/".join(ctx.repo_relative_parts())
    if path in ALLOWED_MACRO_LOAD_PATHS:
        return []
    faults: list[Fault] = []
    node: ast.AST
    for node in ctx.nodes(ast.ImportFrom):
        if isinstance(node, ast.ImportFrom) and any(
            alias.name == LOAD_PROJECT_MACROS_NAME for alias in node.names
        ):
            faults.append(ctx.fault(node=node))
    for node in ctx.nodes(ast.Call):
        if isinstance(node, ast.Call) and call_base_name(node) == LOAD_PROJECT_MACROS_NAME:
            faults.append(ctx.fault(node=node))
    return faults
