"""Build the context required to expand a project's authored SQL bodies."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.attachment.core import build_effective_vars
from sqlbuild.compiler.compile._helpers.render.declarations import (
    build_declaration_scope_resolver,
    build_model_declaration_indexes,
    build_public_declaration_indexes,
)
from sqlbuild.compiler.compile._helpers.render.macros import load_project_macros
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    ConstantDeclaration,
    DeclarationResolutionContext,
    EnumDeclaration,
    LoadedMacro,
    MacroContext,
    SqlExpansionContext,
)
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.exceptions import ScopeValidationError
from sqlbuild.compiler.scopes.main._build_scope_index import build_scope_index
from sqlbuild.compiler.scopes.main._validate_scope_index import validate_scope_index
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.main.resolve_effective_collection_rendering import (
    resolve_effective_collection_rendering,
)


def build_sql_expansion_context(
    *,
    project_dir: Path,
    value_renderer: TypedSqlValueRenderer,
    cli_vars: dict[str, object] | None = None,
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
    loaded_macros: dict[str, LoadedMacro] = load_project_macros(discovered_inputs.macro_files)
    scope_index: ScopeIndex = build_scope_index(
        discovered_inputs=discovered_inputs, loaded_macros=loaded_macros
    )
    try:
        validate_scope_index(index=scope_index)
    except ScopeValidationError as error:
        raise CompileInputError(str(error)) from error
    enums: dict[str, EnumDeclaration]
    constants: dict[str, ConstantDeclaration]
    enums, constants = build_public_declaration_indexes(discovered_inputs=discovered_inputs)
    local_declarations: dict[Path, DeclarationResolutionContext] = {}
    for model_file in discovered_inputs.model_files:
        local_enums: dict[str, EnumDeclaration]
        local_constants: dict[str, ConstantDeclaration]
        local_enums, local_constants = build_model_declaration_indexes(model_file=model_file)
        local_declarations[model_file.file_path] = DeclarationResolutionContext(
            enums=local_enums,
            constants=local_constants,
        )
    return SqlExpansionContext(
        effective_vars=effective_vars,
        loaded_macros=loaded_macros,
        macro_context=MacroContext(
            adapter_name=resolve_effective_adapter_name(
                project_config=discovered_inputs.project_config,
                local_config=discovered_inputs.local_config,
            ),
            sql_analysis_enabled=False,
            target_name=discovered_inputs.project_config.default_target,
            vars=effective_vars,
        ),
        enums=enums,
        constants=constants,
        value_renderer=value_renderer,
        collection_rendering=resolve_effective_collection_rendering(
            project_config=discovered_inputs.project_config,
            declaration_override=None,
        ),
        local_declarations=local_declarations,
        declaration_resolver=build_declaration_scope_resolver(
            discovered_inputs=discovered_inputs,
            scope_index=scope_index,
            loaded_macros=loaded_macros,
        ),
    )
