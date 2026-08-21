"""Build the context required to expand a project's authored SQL bodies."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.attachment.core import build_effective_vars
from sqlbuild.compiler.compile._helpers.render.declarations import (
    build_public_declaration_indexes,
)
from sqlbuild.compiler.compile.main.load_macros import load_macros
from sqlbuild.compiler.compile.models import (
    ConstantDeclaration,
    EnumDeclaration,
    LoadedMacro,
    MacroContext,
    SqlExpansionContext,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs


def build_sql_expansion_context(
    *, project_dir: Path, cli_vars: dict[str, object] | None = None
) -> SqlExpansionContext:
    """Assemble project vars, macros and declarations for SQL expansion."""

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=project_dir, sql_analysis_enabled_override=False
    )
    effective_vars: dict[str, object] = build_effective_vars(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_config=None,
        cli_vars={} if cli_vars is None else cli_vars,
    )
    loaded_macros: dict[str, LoadedMacro] = load_macros(discovered_inputs.macro_files)
    enums: dict[str, EnumDeclaration]
    constants: dict[str, ConstantDeclaration]
    enums, constants = build_public_declaration_indexes(discovered_inputs=discovered_inputs)
    return SqlExpansionContext(
        effective_vars=effective_vars,
        loaded_macros=loaded_macros,
        macro_context=MacroContext(
            adapter_name=discovered_inputs.project_config.adapter,
            sql_analysis_enabled=False,
            target_name=discovered_inputs.project_config.default_target,
            vars=effective_vars,
        ),
        enums=enums,
        constants=constants,
    )
