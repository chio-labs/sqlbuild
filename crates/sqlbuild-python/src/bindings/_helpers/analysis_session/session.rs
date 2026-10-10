//! The native model analysis session and expression-source shapes for the preview engine.

use pyo3::prelude::{Bound, Py, PyAny, PyErr, PyModule, PyModuleMethods, PyRef, PyResult, Python};
use pyo3::types::PyDict;
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_analysis::assembly::analysis_session::main::attach_analysis_cache::attach_analysis_cache;
use sqlbuild_analysis::assembly::analysis_session::main::expression_shapes::expression_shapes;
use sqlbuild_analysis::assembly::analysis_session::main::finish_analysis_session::finish_analysis_session;
use sqlbuild_analysis::assembly::analysis_session::main::finished_fact_models::finished_fact_models;
use sqlbuild_analysis::assembly::analysis_session::main::prove_dynamic_contracts::prove_dynamic_contracts;
use sqlbuild_analysis::assembly::analysis_session::main::prove_finished_dynamic_contracts::prove_finished_dynamic_contracts;
use sqlbuild_analysis::assembly::analysis_session::main::run_analysis_session::run_analysis_session;
use sqlbuild_analysis::assembly::analysis_session::main::session_sharing::session_sharing;
use sqlbuild_analysis::assembly::analysis_session::main::start_analysis_session::start_analysis_session;
use sqlbuild_analysis::assembly::analysis_session::main::take_analysis_cache::take_analysis_cache;
use sqlbuild_analysis::assembly::analysis_session::models::{
    AnalysisCacheStats, AnalysisSession, ColumnFact, DynamicFamily, ExpressionShape,
    ExpressionShapeRequest, FinishedSession, LineageFacts, LineageRow, ModelOutcome,
    ModelReference, ModelRequest, PivotBatchRequest, PivotModel, PivotOutcome, PivotTables,
    SessionOutcome, SessionRequest, SessionStep,
};
use sqlbuild_analysis::assembly::analysis_session::types::{Pairs, Shapes};
use sqlbuild_analysis::semantic_validation::types::DiagnosticRow;

use sqlbuild_cache::store::models::NativeStore;
use sqlbuild_core::constants::PANIC_MESSAGE;
use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;
use sqlbuild_core::panics::main::is_compiler_panic::is_compiler_panic;
use sqlbuild_core::panics::main::native_failure::native_failure;
use std::path::PathBuf;

use crate::bindings::_helpers::analysis_session::nullability_rules::{
    RuleFailure, nullability_callback, raised,
};
use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::cache::native_store::{open_store, save_store};
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
    Option<Pairs>,
    bool,
    Shapes,
    Shapes,
    Shapes,
    Shapes,
    Vec<(String, Vec<FamilyRow>)>,
    Vec<ModelRow>,
);
/// `(publications, failures)`.
type StepRow = (Shapes, Vec<String>);
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
/// One model's pivot SQL and declared families.
type PivotModelRow = (String, Vec<FamilyRow>);
/// The dialect, relation facts and families by table every proof reads, and the models.
type PivotRequestRow = (
    String,
    Shapes,
    Shapes,
    Shapes,
    Vec<(String, Vec<FamilyRow>)>,
    Vec<PivotModelRow>,
);
/// `("absent" | "deferred" | "proof", proof)`.
type ContractRow = (&'static str, Option<ProofRow>);
/// `(hits, misses, stored, why the store was not read or saved)`.
type CacheStatsRow = (usize, usize, usize, Option<String>);
/// `(models, catalog schema additions, analysis-shape names, dynamic pivot proofs)`.
type FinishRow = (Vec<OutcomeRow>, Shapes, Vec<String>, Vec<ContractRow>);

/// One compile's native model analysis; an internal failure raises `NativeCompilerError`.
#[pyclass(module = "sqlbuild._native")]
pub(crate) struct NativeModelAnalysisSession {
    inner: Option<AnalysisSession>,
    finished: Option<FinishedSession>,
    sharing: (usize, usize),
    cache_path: Option<PathBuf>,
    cache_stats: Option<CacheStatsRow>,
    rule_failure: RuleFailure,
}

/// What an internal native failure of the session names.
const SESSION_CONTEXT: &str = "native model analysis";
/// The native store kind holding finished model analyses.
const MODEL_ANALYSIS_STORE_KIND: &str = "model-analyses";

impl NativeModelAnalysisSession {
    /// The finished session later compile stages read, once `finish` has succeeded.
    pub(crate) fn finished_session(&self) -> Option<&FinishedSession> {
        self.finished.as_ref()
    }

    /// The running session, or `NativeCompilerError` once it has failed or finished.
    fn running(&mut self) -> PyResult<AnalysisSession> {
        self.inner
            .take()
            .ok_or_else(|| internal_error("the session is not running"))
    }
}

/// An internal native failure of the session as `NativeCompilerError`.
fn internal_error(reason: &str) -> PyErr {
    if is_compiler_panic(reason) && reason != PANIC_MESSAGE {
        return compiler_error(reason);
    }
    compiler_error(native_failure(SESSION_CONTEXT, reason))
}

#[pymethods]
impl NativeModelAnalysisSession {
    /// Models whose output names and lineage the finished session keeps for later stages.
    #[getter]
    fn fact_models(&self) -> Vec<String> {
        self.finished
            .as_ref()
            .map(finished_fact_models)
            .unwrap_or_default()
    }

    /// Analyse every model; a model's adapter rule exception is raised as it was, any internal
    /// native failure as `NativeCompilerError`.
    fn run(&mut self, py: Python<'_>) -> PyResult<StepRow> {
        let mut session: AnalysisSession = self.running()?;
        let result: Result<(AnalysisSession, SessionStep), String> =
            py.compiler_detach(move || {
                run_analysis_session(&mut session).map(|step| (session, step))
            });
        if let Some(error) = raised(&self.rule_failure) {
            return Err(error);
        }
        let (session, step) = result.map_err(|reason| internal_error(&reason))?;
        self.sharing = session_sharing(&session);
        self.inner = Some(session);
        Ok(step_row(step))
    }

    /// Every model's outcome; saves the cache best-effort.
    fn finish(&mut self, py: Python<'_>) -> PyResult<FinishRow> {
        let mut session: AnalysisSession = self.running()?;
        let cache: Option<(NativeStore, AnalysisCacheStats)> = take_analysis_cache(&mut session);
        let (outcome, finished) = catch_compiler_panic(|| finish_analysis_session(session))
            .map_err(|reason| internal_error(&reason))?;
        self.finished = Some(finished);
        if let (Some((store, stats)), Some(path)) = (cache, self.cache_path.as_ref()) {
            let saved: Option<String> = save_store(py, &store, path, &[])
                .err()
                .map(|error| error.to_string());
            self.cache_stats = Some((stats.hits, stats.misses, stats.stored, saved));
        }
        Ok(finish_row(outcome))
    }

    /// The analysis cache's `(hits, misses, stored, failure)`; None without a cache.
    #[getter]
    fn cache_stats(&self) -> Option<CacheStatsRow> {
        self.cache_stats.clone()
    }

    /// Each model's dynamic pivot proof from the finished session's tables.
    fn prove_dynamic_contracts(
        &self,
        py: Python<'_>,
        models: Vec<PivotModelRow>,
    ) -> PyResult<Vec<ContractRow>> {
        let session: &FinishedSession = self
            .finished
            .as_ref()
            .ok_or_else(|| internal_error("the session has not finished"))?;
        let models: Vec<PivotModel> = models.into_iter().map(pivot_model).collect();
        let outcomes: Vec<PivotOutcome> = py
            .compiler_detach(|| prove_finished_dynamic_contracts(session, &models))
            .map_err(|reason| internal_error(&reason))?;
        Ok(outcomes.into_iter().map(contract_row).collect())
    }

    /// `(shared members, shared members re-analysed alone)` as of the last step.
    #[getter]
    fn sharing(&self) -> (usize, usize) {
        self.sharing
    }
}

/// Start a session on `catalog`.
///
/// `adapter_rules` holds the adapter's own nullability rules by name, with the
/// `InferredNullability` type they take and return; the request names them `python`.
#[pyfunction]
#[pyo3(signature = (catalog, request, cache=None, adapter_rules=None))]
fn start_model_analysis_session(
    py: Python<'_>,
    catalog: PyRef<'_, ProjectCatalog>,
    request: RequestRow,
    cache: Option<(PathBuf, String)>,
    adapter_rules: Option<(Py<PyDict>, Py<PyAny>)>,
) -> PyResult<NativeModelAnalysisSession> {
    let mut request: SessionRequest = session_request(request);
    let rule_failure: RuleFailure = RuleFailure::default();
    request.nullability_callback = adapter_rules
        .map(|(rules, nullability)| nullability_callback(rules, nullability, rule_failure.clone()));
    let catalog = &catalog.inner;
    let mut session: AnalysisSession = py
        .compiler_detach(|| start_analysis_session(request, catalog))
        .map_err(|reason| internal_error(&reason))?;
    let mut cache_path: Option<PathBuf> = None;
    let mut cache_stats: Option<CacheStatsRow> = None;
    if let Some((path, environment)) = cache {
        match open_store(py, &path, MODEL_ANALYSIS_STORE_KIND, &environment) {
            Ok(store) => {
                attach_analysis_cache(&mut session, store);
                cache_path = Some(path);
            }
            Err(error) => cache_stats = Some((0, 0, 0, Some(error.to_string()))),
        }
    }
    Ok(NativeModelAnalysisSession {
        inner: Some(session),
        finished: None,
        sharing: (0, 0),
        cache_path,
        cache_stats,
        rule_failure,
    })
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
        nullability_rules,
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
        nullability_rules,
        nullability_callback: None,
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
    (step.publications, step.failures)
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
        LineageFacts::NativeFacts(rows) => ("facts", lineage_items(rows)),
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

/// Each model's dynamic pivot proof outside any session.
#[pyfunction]
fn prove_dynamic_column_contracts(
    py: Python<'_>,
    request: PivotRequestRow,
) -> PyResult<Vec<ContractRow>> {
    let (dialect, column_types, authoritative_types, column_nullability, by_table, models) =
        request;
    let request = PivotBatchRequest {
        tables: PivotTables {
            dialect,
            column_types,
            authoritative_types,
            column_nullability,
            families_by_table: families_by_table(by_table),
        },
        models: models.into_iter().map(pivot_model).collect(),
    };
    let outcomes: Vec<PivotOutcome> = py
        .compiler_detach(|| prove_dynamic_contracts(&request))
        .map_err(|reason| internal_error(&reason))?;
    Ok(outcomes.into_iter().map(contract_row).collect())
}

fn pivot_model(row: PivotModelRow) -> PivotModel {
    let (sql, families) = row;
    PivotModel {
        sql,
        families: families.into_iter().map(dynamic_family).collect(),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeModelAnalysisSession>()?;
    module.add_function(wrap_pyfunction!(start_model_analysis_session, module)?)?;
    module.add_function(wrap_pyfunction!(infer_expression_source_shapes, module)?)?;
    module.add_function(wrap_pyfunction!(prove_dynamic_column_contracts, module)?)?;
    Ok(())
}
