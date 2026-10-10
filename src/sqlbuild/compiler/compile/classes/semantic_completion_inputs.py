"""Compile-owned inputs of the native semantic completion stage."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.compact import get_complete_schema_binding_request
from sqlbuild.compiler.compile._helpers.assembly.metadata_validation import (
    _audit_errors,
    _names,
    _sql_test_columns,
)
from sqlbuild.compiler.compile._helpers.assembly.native_declarations import (
    known_declared_types,
    known_function_names,
)
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import semantic_shapes
from sqlbuild.compiler.compile._helpers.diagnostics.resource_sql import get_resource_sql_diagnostics
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.sql_analysis.main._identifier_case import ignores_quoted_case
from sqlbuild.compiler.sql_analysis.models import SqlSchemaValidationRequest


class SemanticCompletionInputs:
    """Expose the shapes, revalidation requests and metadata checks semantic completion reads."""

    @staticmethod
    def shapes(project: CompiledProject) -> dict[str, dict[str, str]]:
        """Closed relation shapes, as type recovery, recovery and explanation read them."""

        return semantic_shapes(project=project)

    @staticmethod
    def revalidation_request(
        *, project: CompiledProject, model: CompiledModel, shapes: dict[str, dict[str, str]]
    ) -> SqlSchemaValidationRequest:
        """Type recovery's request revalidating one failed model against `shapes`."""

        return replace(
            get_complete_schema_binding_request(
                query_sql=model.query_sql,
                placeholders=None,
                dialect=project.sql_analysis_dialect,
                known_functions=known_function_names(project.functions),
                known_types=known_declared_types(functions=project.functions, column_types=shapes),
                binding_schema={
                    reference.ref_name: shapes.get(reference.ref_name, {})
                    for reference in model.references
                },
            ),
            catalog=project.binding_catalog,
            quoted_identifiers_ignore_case=ignores_quoted_case(
                connection=project.effective_connection, dialect=project.sql_analysis_dialect
            ),
        )

    @staticmethod
    def metadata_shapes(
        *, project: CompiledProject, profile: ExpressionInferenceProfile
    ) -> dict[str, dict[str, str]]:
        """Closed relation shapes, as the metadata checks read them under `profile`."""

        return semantic_shapes(project=project, profile=profile)

    @staticmethod
    def column_names(value: object) -> tuple[str, ...]:
        """The column names a metadata config value lists."""

        return _names(value)

    @staticmethod
    def audit_diagnostics(
        *,
        model: CompiledModel,
        project: CompiledProject,
        shape: dict[str, str],
        shapes: dict[str, dict[str, str]],
        profile: ExpressionInferenceProfile,
    ) -> tuple[CompilerDiagnostic, ...]:
        """The schema audit checks of one model with a closed shape."""

        return _audit_errors(
            model=model, project=project, shape=shape, shapes=shapes, profile=profile
        )

    @staticmethod
    def sql_test_columns(
        *, project: CompiledProject, profile: ExpressionInferenceProfile
    ) -> dict[str, tuple[str, ...]]:
        """The inferred output columns of every model SQL test CTE body."""

        return _sql_test_columns(project=project, profile=profile)

    @staticmethod
    def resource_sql_diagnostics(
        *,
        project: CompiledProject,
        shapes: dict[str, dict[str, str]],
        profile: ExpressionInferenceProfile,
    ) -> tuple[CompilerDiagnostic, ...]:
        """The compile-time SQL checks of audits, SQL tests and SQL hooks."""

        return tuple(get_resource_sql_diagnostics(project=project, shapes=shapes, profile=profile))
