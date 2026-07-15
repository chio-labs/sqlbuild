"""Repository-specific module placement and shape rules."""

from __future__ import annotations

import ast

from strata import Family, Fault, RuleContext, rule

from scripts.strata_policy._helpers.ast_checks import top_level_class_nodes
from scripts.strata_policy._helpers.path_checks import is_adapter_class_entry
from scripts.strata_policy.constants import (
    CLIENT_MODULE_MIN_PARTS,
    CLIENT_MODULE_NAME,
    CLIENT_STYLE_PREFIXES,
    DEV_TOOLING_FILE_PREFIXES,
    DEV_TOOLING_SEGMENTS,
    FORBIDDEN_GENERIC_FILENAMES,
    MAIN_MODULE_NAME,
    MAIN_PACKAGE_NAME,
    MAIN_SUPPORT_PACKAGE_NAMES,
    POLICY_EVALUATION_SCOPES,
    PROVIDER_CLASS_NAME,
    PROVIDER_MODULE_PARTS,
    ROOT_SCOPE_NAME,
)


@rule(
    code="XSB002",
    family=Family.CUSTOM,
    slug="dev-tooling-location",
    message="development tooling must live under scripts, not product code",
    remediation="Move check, format, lint, and test tooling beneath scripts/.",
)
def dev_tooling_location(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    if ctx.scope() != ROOT_SCOPE_NAME:
        return []
    parts: tuple[str, ...] = ctx.relative_parts()
    if parts[-1].removesuffix(".py").startswith(DEV_TOOLING_FILE_PREFIXES) or any(
        part in DEV_TOOLING_SEGMENTS for part in parts[:-1]
    ):
        return [ctx.path_fault()]
    return []


@rule(
    code="XSB003",
    family=Family.CUSTOM,
    slug="sqlbuild-generic-filename",
    message="generic module filenames hide SQLBuild ownership",
    remediation="Rename the module after the domain concept or operation it owns.",
)
def sqlbuild_generic_filename(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    if ctx.scope() not in POLICY_EVALUATION_SCOPES:
        return []
    return [ctx.path_fault()] if ctx.path.name in FORBIDDEN_GENERIC_FILENAMES else []


@rule(
    code="XSB023",
    family=Family.CUSTOM,
    slug="client-entry-filename",
    message="client-style packages must use client.py instead of main.py",
    remediation="Rename the primary client class entry module to client.py.",
)
def client_entry_filename(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    parts: tuple[str, ...] = ctx.repo_relative_parts()
    if (
        len(parts) >= CLIENT_MODULE_MIN_PARTS
        and parts[:3] in CLIENT_STYLE_PREFIXES
        and parts[-1] == MAIN_MODULE_NAME
    ):
        return [ctx.path_fault()]
    return []


@rule(
    code="XSB024",
    family=Family.CUSTOM,
    slug="client-public-class-count",
    message="client.py must define exactly one public top-level class",
    remediation="Keep one public client class and move other classes to their owning modules.",
)
def client_public_class_count(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    parts: tuple[str, ...] = ctx.repo_relative_parts()
    if (
        len(parts) < CLIENT_MODULE_MIN_PARTS
        or parts[:3] not in CLIENT_STYLE_PREFIXES
        or parts[-1] != CLIENT_MODULE_NAME
    ):
        return []
    public_classes: tuple[ast.ClassDef, ...] = tuple(
        node for node in top_level_class_nodes(module) if not node.name.startswith("_")
    )
    return [ctx.path_fault()] if len(public_classes) != 1 else []


@rule(
    code="XSB025",
    family=Family.CUSTOM,
    slug="client-module-content",
    message="client.py may contain only imports and top-level classes",
    remediation="Move functions and runtime statements into the class or an owned support module.",
)
def client_module_content(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    parts: tuple[str, ...] = ctx.repo_relative_parts()
    if (
        len(parts) < CLIENT_MODULE_MIN_PARTS
        or parts[:3] not in CLIENT_STYLE_PREFIXES
        or parts[-1] != CLIENT_MODULE_NAME
    ):
        return []
    return [
        ctx.fault(node=node)
        for node in ctx.non_docstring_body(module)
        if not isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef))
    ]


@rule(
    code="XSB031",
    family=Family.CUSTOM,
    slug="adapter-entry-class-count",
    message="adapter class entry modules must define exactly one public top-level class",
    remediation="Keep one public adapter class and move other classes to classes/.",
)
def adapter_entry_class_count(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    parts: tuple[str, ...] = ctx.repo_relative_parts()
    if not is_adapter_class_entry(parts=parts):
        return []
    public_classes: tuple[ast.ClassDef, ...] = tuple(
        node for node in top_level_class_nodes(module) if not node.name.startswith("_")
    )
    return [ctx.path_fault()] if len(public_classes) != 1 else []


@rule(
    code="XSB032",
    family=Family.CUSTOM,
    slug="adapter-entry-content",
    message="adapter class entry modules may contain only imports and top-level classes",
    remediation="Move functions and runtime statements into the adapter class or a role boundary.",
)
def adapter_entry_content(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    parts: tuple[str, ...] = ctx.repo_relative_parts()
    if not is_adapter_class_entry(parts=parts):
        return []
    return [
        ctx.fault(node=node)
        for node in ctx.non_docstring_body(module)
        if not isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef))
    ]


@rule(
    code="XSB042",
    family=Family.CUSTOM,
    slug="provider-public-surface",
    message="providers.py must contain imports and exactly one Provider class",
    remediation="Keep only the public Provider class and imports in src/sqlbuild/providers.py.",
)
def provider_public_surface(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    if ctx.repo_relative_parts() != PROVIDER_MODULE_PARTS:
        return []
    faults: list[Fault] = []
    provider_count: int = 0
    node: ast.stmt
    for node in ctx.non_docstring_body(module):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ClassDef) and node.name == PROVIDER_CLASS_NAME:
            provider_count += 1
            continue
        faults.append(ctx.fault(node=node))
    if provider_count != 1:
        faults.append(ctx.path_fault())
    return faults


@rule(
    code="XSB061",
    family=Family.CUSTOM,
    slug="main-support-placement",
    message="main packages must not contain support packages",
    remediation="Move _helpers/, classes/, or shared/ beside main/.",
)
def main_support_placement(*, module: ast.Module, ctx: RuleContext) -> list[Fault]:
    if ctx.scope() not in POLICY_EVALUATION_SCOPES:
        return []
    parts: tuple[str, ...] = ctx.repo_relative_parts()
    for index, part in enumerate(parts[:-1]):
        if part == MAIN_PACKAGE_NAME and parts[index + 1] in MAIN_SUPPORT_PACKAGE_NAMES:
            return [ctx.path_fault()]
    return []
