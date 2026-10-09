"""Hand compiled-project assembly and model analysis to their native stages when enabled."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.main._analyze_native_model_sql import (
    analyze_native_model_sql,
)
from sqlbuild.compiler.analysis_session.main._infer_native_expression_source_shapes import (
    infer_native_expression_source_shapes,
)
from sqlbuild.compiler.analysis_session.main._prove_native_dynamic_contract import (
    prove_native_dynamic_contract,
)
from sqlbuild.compiler.analysis_session.models import NativeModelAnalysisRequest
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import (
    get_expression_source_shapes,
)
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompileProjectInputs,
    DynamicColumnContractProof,
    ModelSqlAnalysis,
)
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.main.report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite, NativeStage
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.project_assembly.main._assemble_native_project import (
    assemble_native_project,
)
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


def assemble_project_by_engine(
    *,
    inputs: CompileProjectInputs,
    inference_profile: ExpressionInferenceProfile | None,
    skip_column_inference: bool,
    column_lineage_mode: ColumnLineageMode,
    analysis_cache_dir: Path | None,
    analysis_model_names: frozenset[str] | None,
) -> CompiledProject | None:
    """Return the natively assembled project, or None where Python must assemble it."""

    if not native_stage_enabled(NativeStage.PROJECT_ASSEMBLY):
        return None
    assembled: CompiledProject | None = assemble_native_project(
        inputs=inputs,
        inference_profile=inference_profile,
        skip_column_inference=skip_column_inference,
        column_lineage_mode=column_lineage_mode,
        analysis_cache_dir=analysis_cache_dir,
        analysis_model_names=analysis_model_names,
    )
    if assembled is not None:
        report_native_answer(stage=NativeStage.PROJECT_ASSEMBLY, kind="project_assemblies")
    else:
        report_native_fallback(site=NativeFallbackSite.PROJECT_ASSEMBLY)
    return assembled


def expression_source_shapes_by_engine(
    *, expressions: tuple[str, ...], profile: ExpressionInferenceProfile
) -> tuple[dict[str, str] | None, ...]:
    """Infer one shape per expression source natively, or with Python where native defers."""

    if native_stage_enabled(NativeStage.MODEL_ANALYSIS):
        native_shapes: tuple[dict[str, str] | None, ...] | None = (
            infer_native_expression_source_shapes(expressions=expressions, profile=profile)
        )
        if native_shapes is not None:
            report_native_answer(
                stage=NativeStage.MODEL_ANALYSIS, kind="expression_shapes", units=len(native_shapes)
            )
            return native_shapes
    return get_expression_source_shapes(expressions=expressions, profile=profile)


def analyze_model_sql_by_engine(
    *,
    python_analysis: partial[dict[str, ModelSqlAnalysis]],
    dynamic_families_by_table: dict[str, tuple[SchemaDynamicColumnFamily, ...]],
) -> dict[str, ModelSqlAnalysis]:
    """Analyze models natively with the Python analysis's arguments, or run the Python analysis."""

    if native_stage_enabled(NativeStage.MODEL_ANALYSIS):
        native_analyses: dict[str, ModelSqlAnalysis] | None = analyze_native_model_sql(
            request=NativeModelAnalysisRequest(
                **python_analysis.keywords, dynamic_families_by_table=dynamic_families_by_table
            )
        )
        if native_analyses is not None:
            report_native_answer(
                stage=NativeStage.MODEL_ANALYSIS, kind="model_analyses", units=len(native_analyses)
            )
            return native_analyses
    return python_analysis()


def dynamic_column_contract_by_engine(
    *,
    sql_analysis: ModelSqlAnalysis | None,
    python_proof: partial[DynamicColumnContractProof | None],
) -> DynamicColumnContractProof | None:
    """Return the proof native analysis carries or proves alone, or prove it in Python."""

    if sql_analysis is not None and sql_analysis.dynamic_column_contract is not None:
        return sql_analysis.dynamic_column_contract
    if (
        sql_analysis is None
        and python_proof.keywords["families"]
        and native_stage_enabled(NativeStage.MODEL_ANALYSIS)
    ):
        native: DynamicColumnContractProof | None = prove_native_dynamic_contract(
            **python_proof.keywords
        )
        if native is not None:
            report_native_answer(stage=NativeStage.MODEL_ANALYSIS, kind="dynamic_contract_proofs")
            return native
    return python_proof()
