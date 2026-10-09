//! The native model analysis session and expression-source shapes for the preview engine.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyRef, PyResult, Python};
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_analysis::assembly::analysis_session::main::expression_shapes::expression_shapes;
use sqlbuild_analysis::assembly::analysis_session::main::finish_analysis_session::finish_analysis_session;
use sqlbuild_analysis::assembly::analysis_session::main::prove_dynamic_contract::prove_dynamic_contract;
use sqlbuild_analysis::assembly::analysis_session::main::provide_deferred_analyses::provide_deferred_analyses;
use sqlbuild_analysis::assembly::analysis_session::main::run_analysis_session::run_analysis_session;
use sqlbuild_analysis::assembly::analysis_session::main::start_analysis_session::start_analysis_session;
use sqlbuild_analysis::assembly::analysis_session::models::{
    AnalysisSession, ColumnFact, Deferral, DeferredAnalysis, DynamicFamily, ExpressionShape,
    ExpressionShapeRequest, LineageFacts, LineageRow, ModelOutcome, ModelReference, ModelRequest,
    PivotOutcome, PivotRequest, SessionOutcome, SessionRequest, SessionStep,
};
use sqlbuild_analysis::assembly::analysis_session::types::{Pairs, Shapes};
use sqlbuild_analysis::semantic_validation::types::DiagnosticRow;

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::models::ProjectCatalog;
use crate::bindings::types::CompilerDetach;

/// `(name, type, nullability)`.
type ColumnRow = (String, Option<String>, String);
/// `(output column, transform code, confidence code, [(resource type, resource, column)])`.
type LineageItem = (String, u8, u8, Vec<(String, String, String)>);
/// `(name, pivot column, value column, aggregate, type, name pattern)`.
type FamilyRow = (String, String, String, String, String, Option<String>);
/// A model's name, SQL, placeholders, references, lineage, required names, flags and pivot.
type ModelRow = (
    String,
    String,
    Pairs,
    Vec<(String, bool)>,
    Vec<(String, String, String)>,
    Vec<String>,
    bool,
    bool,
    Option<(String, String)>,
    String,
    Vec<FamilyRow>,
);
/// The profile settings, relation shapes and models one session analyses.
type RequestRow = (
    String,
    bool,
    Pairs,
    bool,
    Shapes,
    Shapes,
    Shapes,
    Shapes,
    Vec<(String, Vec<FamilyRow>)>,
    Vec<ModelRow>,
);
/// `(kind, model, cleaned_sql, schemas, binding diagnostics, lineage)`.
type DeferralRow = (
    &'static str,
    usize,
    Option<String>,
    Shapes,
    Vec<DiagnosticRow>,
    Option<Vec<LineageItem>>,
);
/// `(publications, deferrals, failures)`.
type StepRow = (Shapes, Vec<DeferralRow>, Vec<String>);
/// `(model, succeeded, columns, has_star, star_resolved, binding diagnostics, validated)`.
type DeferredRow = (
    usize,
    bool,
    Option<Vec<ColumnRow>>,
    bool,
    bool,
    Vec<DiagnosticRow>,
    bool,
);
/// One model's analysis, lineage source and cleaned SQL.
type OutcomeRow = (
    bool,
    Option<Vec<ColumnRow>>,
    &'static str,
    Vec<LineageItem>,
    bool,
    bool,
    Vec<DiagnosticRow>,
    bool,
    String,
);
/// `(output proven, fixed columns, (family, inferred type), inputs, failure, bare pivot)`.
type ProofRow = (
    bool,
    Vec<ColumnRow>,
    Vec<(String, Option<String>)>,
    Vec<String>,
    Option<String>,
    bool,
);
/// The dialect, relation facts, families by table, SQL and families of one pivot proof.
type PivotRequestRow = (
    String,
    Shapes,
    Shapes,
    Shapes,
    Vec<(String, Vec<FamilyRow>)>,
    String,
    Vec<FamilyRow>,
);
/// `("absent" | "deferred" | "proof", proof)`.
type ContractRow = (&'static str, Option<ProofRow>);
/// `(models, catalog schema additions, analysis-shape names, dynamic pivot proofs)`.
type FinishRow = (Vec<OutcomeRow>, Shapes, Vec<String>, Vec<ContractRow>);

/// One compile's native model analysis; any failure hands the whole analysis back to Python.
#[pyclass(module = "sqlbuild._native")]
pub(crate) struct NativeModelAnalysisSession {
    inner: Option<AnalysisSession>,
    failure: Option<String>,
}

impl NativeModelAnalysisSession {
    /// Keep `result`'s value, or end the session and keep its failure for Python's debug log.
    fn kept<T>(&mut self, result: Result<T, String>) -> Option<T> {
        match result {
            Ok(value) => Some(value),
            Err(error) => {
                self.inner = None;
                self.failure = Some(error);
                None
            }
        }
    }
}

#[pymethods]
impl NativeModelAnalysisSession {
    /// Advance; None means Python must analyse every model, no deferrals means done.
    fn run(&mut self, py: Python<'_>) -> Option<StepRow> {
        let mut session: AnalysisSession = self.inner.take()?;
        let result: Result<(AnalysisSession, SessionStep), String> =
            py.compiler_detach(move || {
                run_analysis_session(&mut session).map(|step| (session, step))
            });
        let (session, step) = self.kept(result)?;
        self.inner = Some(session);
        Some(step_row(step))
    }

    /// Answer the last step's deferrals; False means Python must analyse every model.
    fn provide(&mut self, results: Vec<DeferredRow>) -> bool {
        let Some(mut session) = self.inner.take() else {
            return false;
        };
        let answers: Vec<DeferredAnalysis> = results.into_iter().map(deferred_analysis).collect();
        let provided: Result<(), String> =
            catch_compiler_panic(|| provide_deferred_analyses(&mut session, answers));
        self.inner = Some(session);
        self.kept(provided).is_some()
    }

    /// Every model's outcome once the session is done, or None to analyse in Python.
    fn finish(&mut self) -> Option<FinishRow> {
        let session: AnalysisSession = self.inner.take()?;
        let outcome: Result<FinishRow, String> =
            catch_compiler_panic(|| finish_analysis_session(session).map(finish_row));
        self.kept(outcome)
    }

    /// Why the session handed the analysis back to Python, when it did.
    #[getter]
    fn failure(&self) -> Option<String> {
        self.failure.clone()
    }
}

/// Start a session on `catalog`, or None where Python must analyse.
#[pyfunction]
fn start_model_analysis_session(
    py: Python<'_>,
    catalog: PyRef<'_, ProjectCatalog>,
    request: RequestRow,
) -> PyResult<Option<NativeModelAnalysisSession>> {
    let request: SessionRequest = session_request(request);
    let catalog = &catalog.inner;
    let session: Option<AnalysisSession> = py
        .compiler_detach(|| Ok(start_analysis_session(request, catalog)))
        .map_err(compiler_error)?;
    Ok(session.map(|session| NativeModelAnalysisSession {
        inner: Some(session),
        failure: None,
    }))
}

/// Each expression's shape, with `False` where Python must infer it.
#[pyfunction]
fn infer_expression_source_shapes(
    py: Python<'_>,
    catalog: PyRef<'_, ProjectCatalog>,
    request: (String, bool, Pairs, Vec<String>),
) -> (Vec<(bool, Option<Pairs>)>, Option<String>) {
    let (dialect, case_sensitive_shapes, function_return_types, expressions) = request;
    let request = ExpressionShapeRequest {
        dialect,
        case_sensitive_shapes,
        function_return_types,
        expressions,
    };
    let catalog = &catalog.inner;
    match py.compiler_detach(|| expression_shapes(catalog, &request)) {
        Ok(shapes) => (shapes.into_iter().map(expression_shape_row).collect(), None),
        Err(error) => (Vec::new(), Some(error)),
    }
}

fn expression_shape_row(shape: ExpressionShape) -> (bool, Option<Pairs>) {
    match shape {
        ExpressionShape::Inferred(shape) => (true, Some(shape)),
        ExpressionShape::Absent => (true, None),
        ExpressionShape::Deferred => (false, None),
    }
}

fn session_request(request: RequestRow) -> SessionRequest {
    let (
        dialect,
        case_sensitive_shapes,
        function_return_types,
        rich_type_inference,
        column_types,
        column_nullability,
        complete_schemas,
        catalog_schemas,
        dynamic_families_by_table,
        models,
    ) = request;
    SessionRequest {
        dialect,
        case_sensitive_shapes,
        function_return_types,
        rich_type_inference,
        column_types,
        column_nullability,
        complete_schemas,
        catalog_schemas,
        dynamic_families_by_table: families_by_table(dynamic_families_by_table),
        models: models.into_iter().map(model_request).collect(),
    }
}

fn model_request(row: ModelRow) -> ModelRequest {
    let (
        name,
        query_sql,
        placeholders,
        references,
        lineage_references,
        required_names,
        recover_cte_facts,
        has_set_operation,
        snapshot_columns,
        pivot_sql,
        dynamic_families,
    ) = row;
    ModelRequest {
        name,
        query_sql,
        placeholders,
        references: references
            .into_iter()
            .map(|(analysis_name, model_ref)| ModelReference {
                analysis_name,
                model_ref,
            })
            .collect(),
        lineage_references,
        required_names,
        recover_cte_facts,
        has_set_operation,
        snapshot_columns,
        pivot_sql,
        dynamic_families: dynamic_families.into_iter().map(dynamic_family).collect(),
    }
}

fn step_row(step: SessionStep) -> StepRow {
    (
        step.publications,
        step.deferrals.into_iter().map(deferral_row).collect(),
        step.failures,
    )
}

fn deferral_row(deferral: Deferral) -> DeferralRow {
    let kind: &'static str = deferral.kind();
    match deferral {
        Deferral::Analysis {
            model,
            cleaned_sql,
            binding_schema,
            binding_diagnostics,
            lineage,
        } => (
            kind,
            model,
            Some(cleaned_sql),
            binding_schema,
            binding_diagnostics,
            lineage.map(lineage_items),
        ),
        Deferral::Enrichment {
            model,
            input_schemas,
        } => (kind, model, None, input_schemas, Vec::new(), None),
    }
}

fn deferred_analysis(row: DeferredRow) -> DeferredAnalysis {
    let (model, analysis_succeeded, columns, has_star, star_resolved, diagnostics, validated) = row;
    DeferredAnalysis {
        model,
        analysis_succeeded,
        columns: columns.map(|columns| columns.into_iter().map(column_fact).collect()),
        has_star,
        star_resolved,
        binding_diagnostics: diagnostics,
        binding_validated: validated,
    }
}

fn column_fact((name, data_type, nullability): ColumnRow) -> ColumnFact {
    ColumnFact {
        name,
        data_type,
        nullability,
    }
}

fn column_row(column: ColumnFact) -> ColumnRow {
    (column.name, column.data_type, column.nullability)
}

fn lineage_items(rows: Vec<LineageRow>) -> Vec<LineageItem> {
    rows.into_iter()
        .map(|row| {
            (
                row.output_column,
                row.transform_code,
                row.confidence_code,
                row.sources,
            )
        })
        .collect()
}

fn finish_row(outcome: SessionOutcome) -> FinishRow {
    (
        outcome.models.into_iter().map(outcome_row).collect(),
        outcome.schema_additions,
        outcome.analysis_names,
        outcome
            .dynamic_contracts
            .into_iter()
            .map(contract_row)
            .collect(),
    )
}

fn families_by_table(rows: Vec<(String, Vec<FamilyRow>)>) -> Vec<(String, Vec<DynamicFamily>)> {
    rows.into_iter()
        .map(|(name, families)| (name, families.into_iter().map(dynamic_family).collect()))
        .collect()
}

fn dynamic_family(row: FamilyRow) -> DynamicFamily {
    let (name, pivot_column, value_column, aggregate, data_type, name_pattern) = row;
    DynamicFamily {
        name,
        pivot_column,
        value_column,
        aggregate,
        data_type,
        name_pattern,
    }
}

fn contract_row(outcome: PivotOutcome) -> ContractRow {
    match outcome {
        PivotOutcome::Absent => ("absent", None),
        PivotOutcome::Deferred => ("deferred", None),
        PivotOutcome::Proof(proof) => (
            "proof",
            Some((
                proof.output_proven,
                proof.fixed_columns.into_iter().map(column_row).collect(),
                proof.families,
                proof.input_relations,
                proof.failure_reason,
                proof.bare_dynamic_pivot,
            )),
        ),
    }
}

fn outcome_row(outcome: ModelOutcome) -> OutcomeRow {
    let analysis = outcome.analysis;
    let (source, lineage) = match analysis.lineage {
        LineageFacts::Native(rows) => ("native", lineage_items(rows)),
        LineageFacts::PythonAnalysis => ("analysis", Vec::new()),
        LineageFacts::PythonEnrichment => ("enrichment", Vec::new()),
        LineageFacts::NativeEnrichment(rows) => ("facts", lineage_items(rows)),
    };
    (
        analysis.analysis_succeeded,
        analysis
            .columns
            .map(|columns| columns.into_iter().map(column_row).collect()),
        source,
        lineage,
        analysis.has_star,
        analysis.star_resolved,
        analysis.binding_diagnostics,
        analysis.binding_validated,
        outcome.cleaned_sql,
    )
}

/// One model's dynamic pivot proof, or `("deferred", None)` for Python's proof.
#[pyfunction]
fn prove_dynamic_column_contract(py: Python<'_>, request: PivotRequestRow) -> ContractRow {
    let (dialect, column_types, authoritative_types, column_nullability, by_table, sql, families) =
        request;
    let request = PivotRequest {
        dialect,
        column_types,
        authoritative_types,
        column_nullability,
        families_by_table: families_by_table(by_table),
        sql,
        families: families.into_iter().map(dynamic_family).collect(),
    };
    py.compiler_detach(|| prove_dynamic_contract(&request))
        .map_or(("deferred", None), contract_row)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeModelAnalysisSession>()?;
    module.add_function(wrap_pyfunction!(start_model_analysis_session, module)?)?;
    module.add_function(wrap_pyfunction!(infer_expression_source_shapes, module)?)?;
    module.add_function(wrap_pyfunction!(prove_dynamic_column_contract, module)?)?;
    Ok(())
}
