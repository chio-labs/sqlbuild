"""Build a compiled project with target defaults and adapter-aware validation."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.assemble_project import assemble_project
from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompileProjectInputs,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.pipeline._helpers.target_defaults import apply_target_defaults
from sqlbuild.compiler.pipeline._helpers.target_validation import validate_project_targets
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def build_compiled_project(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    selected_target: str | None = None,
    no_sql_validation: bool = False,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ColumnLineageMode.FAST,
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    resolved_connection: dict[str, object] | None = None,
) -> CompiledProject:
    """Build one compiled project with adapter defaults and target validation applied."""

    compile_inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs=discovered_inputs,
        selected_target=selected_target,
        no_sql_validation=no_sql_validation,
        defer_model_sql_validation=True,
        cli_vars=cli_vars,
        resolved_connection=resolved_connection,
        python_functions_inherit_default_namespace=(
            adapter.python_functions_inherit_default_namespace()
        ),
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    project: CompiledProject = apply_target_defaults(
        project=assemble_project(
            inputs=compile_inputs,
            inference_profile=adapter.expression_inference_profile(),
            skip_column_inference=skip_column_inference,
            column_lineage_mode=column_lineage_mode,
        ),
        default_schema=adapter.default_schema(),
        default_database=adapter.default_database(),
        render_qualified_name=adapter.render_qualified_name,
        python_functions_inherit_default_namespace=(
            adapter.python_functions_inherit_default_namespace()
        ),
    )
    validate_project_targets(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project=project,
    )
    return project
