use crate::assembly::analysis_session::_helpers::mappings::catalog_relations;
use crate::assembly::analysis_session::main::finish_analysis_session::finish_analysis_session;
use crate::assembly::analysis_session::main::provide_deferred_analyses::provide_deferred_analyses;
use crate::assembly::analysis_session::main::run_analysis_session::run_analysis_session;
use crate::assembly::analysis_session::main::start_analysis_session::start_analysis_session;
use crate::assembly::analysis_session::models::{
    AnalysisSession, Deferral, DeferredAnalysis, ModelOutcome, ModelReference, ModelRequest,
    SessionRequest, SessionStep,
};
use crate::assembly::analysis_session::tests::test_types::ModelSpec;
use crate::assembly::analysis_session::types::{Pairs, Shapes};
use crate::semantic_validation::models::{CatalogInput, ProjectCatalog};

pub(crate) fn pairs(values: &[(&str, &str)]) -> Pairs {
    values
        .iter()
        .map(|(name, value)| ((*name).to_owned(), (*value).to_owned()))
        .collect()
}

pub(crate) fn shapes(values: &[(&str, &[(&str, &str)])]) -> Shapes {
    values
        .iter()
        .map(|(name, shape)| ((*name).to_owned(), pairs(shape)))
        .collect()
}

/// The compile catalog holding the closed `relations` Python registered before analysis.
pub(crate) fn catalog(dialect: &str, relations: &Shapes) -> ProjectCatalog {
    ProjectCatalog::new(CatalogInput {
        dialect: dialect.to_owned(),
        quoted_ignore_case: false,
        known_functions: Vec::new(),
        known_types: Vec::new(),
        relations: catalog_relations(relations),
    })
    .expect("the catalog dialect is known")
}

/// A model reading `sources` (source names) and `refs` (model names).
pub(crate) fn model(name: &str, sql: &str, sources: &[&str], refs: &[&str]) -> ModelRequest {
    let mut references: Vec<ModelReference> = Vec::new();
    let mut lineage_references: Vec<(String, String, String)> = Vec::new();
    for source in sources {
        references.push(ModelReference {
            analysis_name: (*source).to_owned(),
            model_ref: false,
        });
        lineage_references.push((
            (*source).to_owned(),
            "source".to_owned(),
            (*source).to_owned(),
        ));
    }
    for model_ref in refs {
        references.push(ModelReference {
            analysis_name: (*model_ref).to_owned(),
            model_ref: true,
        });
        lineage_references.push((
            (*model_ref).to_owned(),
            "model".to_owned(),
            (*model_ref).to_owned(),
        ));
    }
    let mut required_names: Vec<String> = sources
        .iter()
        .chain(refs)
        .map(|name| (*name).to_owned())
        .collect();
    required_names.sort();
    ModelRequest {
        name: name.to_owned(),
        query_sql: sql.to_owned(),
        placeholders: Vec::new(),
        references,
        lineage_references,
        required_names,
        recover_cte_facts: false,
        has_set_operation: sql.contains("UNION"),
        snapshot_columns: None,
    }
}

/// A DuckDB request whose `raw_orders` source is closed and typed.
pub(crate) fn orders_request(models: Vec<ModelRequest>) -> SessionRequest {
    let raw_orders: Shapes = shapes(&[(
        "raw_orders",
        &[("order_id", "INTEGER"), ("amount", "DOUBLE")],
    )]);
    SessionRequest {
        dialect: "duckdb".to_owned(),
        case_sensitive_shapes: false,
        function_return_types: Vec::new(),
        rich_type_inference: true,
        column_types: raw_orders.clone(),
        column_nullability: shapes(&[(
            "raw_orders",
            &[("order_id", "non_null"), ("amount", "unknown")],
        )]),
        complete_schemas: raw_orders.clone(),
        catalog_schemas: raw_orders,
        models,
    }
}

pub(crate) fn started(request: SessionRequest) -> AnalysisSession {
    let catalog: ProjectCatalog = catalog(&request.dialect, &request.catalog_schemas);
    start_analysis_session(request, &catalog).expect("the models form no cycle")
}

/// Run to completion, answering every deferral with `answer`; return the steps and outcomes.
pub(crate) fn completed(
    mut session: AnalysisSession,
    answer: fn(&Deferral) -> DeferredAnalysis,
) -> (Vec<SessionStep>, Vec<ModelOutcome>) {
    let mut done: bool = false;
    let steps: Vec<SessionStep> = std::iter::from_fn(|| {
        (!done).then(|| {
            let step: SessionStep = run_analysis_session(&mut session).expect("the session runs");
            let answers: Vec<DeferredAnalysis> = step.deferrals.iter().map(answer).collect();
            done = answers.is_empty();
            (!done).then(|| {
                provide_deferred_analyses(&mut session, answers).expect("the answers match")
            });
            step
        })
    })
    .collect();
    let outcome = finish_analysis_session(session).expect("the session finished");
    (steps, outcome.models)
}

/// `name type nullability` per column, or `failed` when analysis did not succeed.
pub(crate) fn described(outcome: &ModelOutcome) -> Vec<String> {
    let analysis = &outcome.analysis;
    let mut lines: Vec<String> = analysis
        .columns
        .iter()
        .flatten()
        .map(|column| {
            format!(
                "{} {} {}",
                column.name,
                column.data_type.as_deref().unwrap_or("-"),
                column.nullability
            )
        })
        .collect();
    lines.push(format!(
        "succeeded={} star={}/{} diagnostics={:?}",
        analysis.analysis_succeeded,
        analysis.has_star,
        analysis.star_resolved,
        analysis
            .binding_diagnostics
            .iter()
            .map(|row| row.0.as_str())
            .collect::<Vec<_>>()
    ));
    lines
}

/// A successful Python answer with no columns and no star.
pub(crate) fn empty_answer(deferral: &Deferral) -> DeferredAnalysis {
    DeferredAnalysis {
        model: deferral.model(),
        analysis_succeeded: true,
        columns: None,
        has_star: false,
        star_resolved: false,
        binding_diagnostics: Vec::new(),
        binding_validated: true,
    }
}

/// `publish name col:TYPE ...` per publication, then `defer kind model` per deferral.
pub(crate) fn step_lines(step: &SessionStep) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    for (name, shape) in &step.publications {
        let columns: Vec<String> = shape
            .iter()
            .map(|(column, data_type)| format!("{column}:{data_type}"))
            .collect();
        lines.push(format!("publish {name} {}", columns.join(" ")));
    }
    lines.extend(
        step.deferrals
            .iter()
            .map(|deferral| format!("defer {} {}", deferral.kind(), deferral.model())),
    );
    lines
}

pub(crate) fn model_requests(models: &[ModelSpec]) -> Vec<ModelRequest> {
    models
        .iter()
        .map(|(name, sql, sources, refs)| model(name, sql, sources, refs))
        .collect()
}

/// Run `models` over the orders request: each step's lines and each model's description.
pub(crate) fn session_lines(models: &[ModelSpec]) -> (Vec<Vec<String>>, Vec<Vec<String>>) {
    let (steps, outcomes) = completed(
        started(orders_request(model_requests(models))),
        empty_answer,
    );
    (
        steps.iter().map(step_lines).collect(),
        outcomes.iter().map(described).collect(),
    )
}
