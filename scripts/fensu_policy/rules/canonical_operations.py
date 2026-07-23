"""Repository-specific canonical operation ownership rules."""

from __future__ import annotations

from fensu import Family, Fault, ImportFact, NamedCallFact, RuleContext, rule

from scripts.fensu_policy._helpers.canonical_operations import (
    call_parses_selector_marker,
    comparison_uses_dbt_ref,
)
from scripts.fensu_policy.constants import (
    ALLOWED_DBT_REF_SCAN_PATHS,
    ALLOWED_MACRO_LOAD_PATHS,
    ALLOWED_SELECTOR_PARSE_PATH,
    ALLOWED_SOURCE_FRESHNESS_INSERT_PREFIXES,
    DBT_INTEGRATION_PATH_PREFIX,
    GRAPH_KEY_CLASS_NAMES,
    INSERT_SQL_PREFIX,
    LOAD_PROJECT_MACROS_NAME,
    NAME_REFERENCE_KIND,
    PLANNER_PATH_PREFIX,
    POLICY_EVALUATION_SCOPES,
    PUBLIC_COLOR_ENTRY_PARTS,
    ROOT_SCOPE_NAME,
    SOURCE_FRESHNESS_MARKERS,
    SOURCE_FRESHNESS_SINGULAR_WRITER,
)


@rule(
    code="XSB041",
    family=Family.CUSTOM,
    slug="color-capability-entry",
    message="color capability imports must use the presentation main entry",
    remediation="Import supports_color from sqlbuild.presentation.main.supports_color.",
)
def color_capability_entry(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.repo_relative_parts() == PUBLIC_COLOR_ENTRY_PARTS:
        return []
    raw_module_parts: tuple[str, ...] = tuple(
        "sqlbuild.presentation._helpers.terminal_capabilities".split(".")
    )
    faults: list[Fault] = []
    imported: ImportFact
    for imported in ctx.facts.references().imports:
        imports_raw_module: bool = imported.module_parts == raw_module_parts or any(
            alias.imported_parts == raw_module_parts for alias in imported.aliases
        )
        if imports_raw_module:
            faults.append(ctx.fault_at(location=imported.location))
    return faults


@rule(
    code="XSB052",
    family=Family.CUSTOM,
    slug="dbt-reference-resolution",
    message="dbt references must be identified by the centralized manifest resolver",
    remediation="Resolve __dbt_ref through integrations/dbt/_helpers/manifest/sqlbuild_refs.py.",
)
def dbt_reference_resolution(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    path: str = "/".join(ctx.repo_relative_parts())
    if DBT_INTEGRATION_PATH_PREFIX not in path or path in ALLOWED_DBT_REF_SCAN_PATHS:
        return []
    return [
        ctx.fault_at(location=comparison.location)
        for comparison in ctx.facts.comparisons()
        if comparison_uses_dbt_ref(comparison=comparison)
    ]


@rule(
    code="XSB053",
    family=Family.CUSTOM,
    slug="dbt-graph-projection",
    message="dbt graph keys must be constructed by the centralized projection helper",
    remediation="Use integrations/dbt/_helpers/planning/graph_projection.py.",
)
def dbt_graph_projection(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    path: str = "/".join(ctx.repo_relative_parts())
    if DBT_INTEGRATION_PATH_PREFIX not in path or path.endswith(
        "src/sqlbuild/integrations/dbt/_helpers/planning/graph_projection.py"
    ):
        return []
    return [
        ctx.fault_at(location=call.location)
        for call in ctx.facts.named_calls()
        if call.reference is not None and call.reference.base_name in GRAPH_KEY_CLASS_NAMES
    ]


@rule(
    code="XSB054",
    family=Family.CUSTOM,
    slug="selector-marker-parsing",
    message="selector + markers must be parsed by split_selector_expansion",
    remediation="Use compiler.planner.main.selection.selector_expansion.split_selector_expansion.",
)
def selector_marker_parsing(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    path: str = "/".join(ctx.repo_relative_parts())
    if (
        not (DBT_INTEGRATION_PATH_PREFIX in path or PLANNER_PATH_PREFIX in path)
        or path == ALLOWED_SELECTOR_PARSE_PATH
    ):
        return []
    return [
        ctx.fault_at(location=call.location)
        for call in ctx.facts.named_calls()
        if call_parses_selector_marker(call=call)
    ]


@rule(
    code="XSB057",
    family=Family.CUSTOM,
    slug="source-freshness-batch-write",
    message="source freshness state must be written in batches",
    remediation="Use write_source_freshness_records() instead of the singular writer.",
)
def source_freshness_batch_write(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() not in POLICY_EVALUATION_SCOPES:
        return []
    faults: list[Fault] = []
    imported: ImportFact
    for imported in ctx.facts.references().imports:
        if imported.from_import and any(
            alias.imported_name == SOURCE_FRESHNESS_SINGULAR_WRITER for alias in imported.aliases
        ):
            faults.append(ctx.fault_at(location=imported.location))
    call: NamedCallFact
    for call in ctx.facts.named_calls():
        if (
            call.reference is not None
            and call.reference.kind == NAME_REFERENCE_KIND
            and call.reference.base_name == SOURCE_FRESHNESS_SINGULAR_WRITER
        ):
            faults.append(ctx.fault_at(location=call.location))
    return faults


@rule(
    code="XSB058",
    family=Family.CUSTOM,
    slug="source-freshness-sql-ownership",
    message="source freshness INSERT SQL must be rendered by adapters",
    remediation="Move source freshness INSERT rendering to the adapter contract.",
)
def source_freshness_sql_ownership(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
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
def single_macro_load_site(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() != ROOT_SCOPE_NAME:
        return []
    path: str = "/".join(ctx.repo_relative_parts())
    if path in ALLOWED_MACRO_LOAD_PATHS:
        return []
    faults: list[Fault] = []
    imported: ImportFact
    for imported in ctx.facts.references().imports:
        if imported.from_import and any(
            alias.imported_name == LOAD_PROJECT_MACROS_NAME for alias in imported.aliases
        ):
            faults.append(ctx.fault_at(location=imported.location))
    call: NamedCallFact
    for call in ctx.facts.named_calls():
        if call.reference is not None and call.reference.base_name == LOAD_PROJECT_MACROS_NAME:
            faults.append(ctx.fault_at(location=call.location))
    return faults
