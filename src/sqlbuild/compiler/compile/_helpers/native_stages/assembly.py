"""Hand compiled-project assembly and model analysis to their native stages when enabled."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.main._analyze_native_model_sql import (
    analyze_native_model_sql,
)
from sqlbuild.compiler.analysis_session.main._infer_native_expression_source_shapes import (
    infer_native_expression_source_shapes,
)
from sqlbuild.compiler.analysis_session.main._prove_native_dynamic_contracts import (
    prove_native_dynamic_contracts,
)
from sqlbuild.compiler.analysis_session.models import (
    NativeModelAnalyses,
    NativeModelAnalysisRequest,
    NativePivotTables,
)
from sqlbuild.compiler.analysis_session.types import ProofRow
from sqlbuild.compiler.compile._helpers.analysis.pivot_requests import standalone_pivot_models
from sqlbuild.compiler.compile._helpers.analysis.syntax_checks import model_syntax_checks
from sqlbuild.compiler.compile.types import CompileInputsView
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.compiler.project_assembly.main._assemble_native_project_resources import (
    assemble_native_project_resources,
)
from sqlbuild.compiler.project_assembly.models import (
    NativeModelFacts,
    NativeProjectFacts,
    NativeProjectResources,
)
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


def native_project_facts(
    *,
    inputs: CompileInputsView,
    dialect: str | None,
    analysis_model_names: frozenset[str] | None,
    analyses: NativeModelAnalyses | None,
    session: Any | None,
    column_types_by_table: dict[str, dict[str, str]],
    authoritative_column_types_by_table: dict[str, dict[str, str]],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    dynamic_families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]],
) -> NativeProjectFacts:
    """Return the native project facts."""

    resources: NativeProjectResources = assemble_native_project_resources(
        inputs=inputs,
        dialect=dialect,
        syntax_checks=model_syntax_checks(
            model_inputs=inputs.model_inputs,
            analysis_model_names=analysis_model_names,
            analysis_succeeded=frozenset() if analyses is None else analyses.succeeded,
        ),
    )
    pivots: dict[int, tuple[str, tuple[SchemaDynamicColumnFamily, ...]]] = standalone_pivot_models(
        model_inputs=inputs.model_inputs, analysed={} if analyses is None else analyses.positions
    )
    proofs: dict[int, ProofRow | None] = dict(
        zip(
            pivots,
            prove_native_dynamic_contracts(
                session=session,
                tables=NativePivotTables(
                    dialect=dialect,
                    column_types_by_table=column_types_by_table,
                    authoritative_column_types_by_table=authoritative_column_types_by_table,
                    column_nullability_by_table=column_nullability_by_table,
                    dynamic_families_by_table=dynamic_families_by_table,
                ),
                models=tuple(pivots.values()),
            ),
            strict=True,
        )
    )
    return NativeProjectFacts(
        models=tuple(
            NativeModelFacts(
                deps=resources.model_deps[index],
                dynamic_contract=proofs.get(index),
                syntax_valid=resources.model_syntax_valid[index],
            )
            for index in range(len(inputs.model_inputs))
        ),
        resources=resources,
    )


def expression_source_shapes(
    *, expressions: tuple[str, ...], profile: ExpressionInferenceProfile
) -> tuple[dict[str, str] | None, ...]:
    """Infer one shape per expression source natively."""

    return infer_native_expression_source_shapes(expressions=expressions, profile=profile)


def analyze_model_sql(request: NativeModelAnalysisRequest) -> NativeModelAnalyses:
    """Analyze models natively; their outcomes stay in the finished session."""

    return analyze_native_model_sql(request=request)
