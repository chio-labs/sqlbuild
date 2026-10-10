//! Python's resource assembly facts for one project, computed natively for the preview engine.

use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::assembly::analysis_session::types::Pairs;
use sqlbuild_analysis::assembly::project::main::assemble_project_resources::assemble_project_resources;
use sqlbuild_analysis::assembly::project::main::check_sql_syntax::check_sql_syntax;
use sqlbuild_analysis::assembly::project::main::sql_syntax_error::sql_syntax_error as check_syntax_error;
use sqlbuild_analysis::assembly::project::models::{
    AuditFacts, InputRead, ModelFacts, Namespace, ProjectRequest, ProjectResources, Reference,
    SeedDefaults, SeedFacts, SourceFacts, SyntaxCheck, SyntaxFailure, SyntaxMode, TargetNamespace,
    Variable,
};
use sqlbuild_analysis::assembly::project::types::ObjectKey;
use sqlbuild_model_config::templates::models::Scalar;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

const TEXT_VARIABLE: &str = "text";
const BOOLEAN_VARIABLE: &str = "bool";
const NONE_VARIABLE: &str = "none";
const TRUE_TEXT: &str = "1";
const ENVIRONMENT_READ: &str = "env";
const CONTEXT_READ: &str = "ctx";

/// `(kind, name, package)`.
type ReferenceRow = (String, String, Option<String>);
/// `(database, schema, loader schema)`.
type TargetRow = (Option<String>, Option<String>, Option<String>);
/// `(database, schema, seed database, seed schema)`.
type DefaultsRow = (
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
);
/// `(name, kind, text)`; kind `text` (also exact ints), `bool`, `none` or anything else.
type VariableRow = (String, String, String);
/// `(references, [(sql, placeholders)])`.
type ModelRow = (Vec<ReferenceRow>, Vec<(String, Pairs)>);
/// `(name, managed, database, schema)`.
type SourceRow = (String, bool, Option<String>, Option<String>);
/// `(name, database, schema)`.
type SeedRow = (String, Option<String>, Option<String>);
/// `(references, attached (kind, name))`.
type AuditRow = (Vec<ReferenceRow>, Option<(String, String)>);
/// The dialect, target, defaults, variables, environment and resources one project assembles.
type RequestRow = (
    String,
    Option<TargetRow>,
    DefaultsRow,
    Vec<VariableRow>,
    Vec<(String, Option<String>)>,
    Vec<ModelRow>,
    Vec<SourceRow>,
    Vec<SeedRow>,
    Vec<Vec<ReferenceRow>>,
    Vec<AuditRow>,
);
/// `(database, schema, logical database, logical schema)`.
type NamespaceRow = (
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
);
/// Deps, managed source and seed namespaces, and the `(env or ctx, name)` template reads.
type ResourcesRow = (
    Vec<Vec<ObjectKey>>,
    Vec<Option<(Option<String>, Option<String>)>>,
    Vec<NamespaceRow>,
    Vec<Vec<ObjectKey>>,
    Vec<Vec<ObjectKey>>,
    Vec<(&'static str, String)>,
    Vec<bool>,
);

/// The project's resource facts, or None with the reason Python must assemble it.
#[pyfunction]
fn assemble_project_resource_facts(
    py: Python<'_>,
    request: RequestRow,
) -> (Option<ResourcesRow>, Option<String>) {
    let request: ProjectRequest = project_request(request);
    match py.compiler_detach(|| assemble_project_resources(&request)) {
        Ok(resources) => (Some(resources_row(resources)), None),
        Err(reason) => (None, Some(reason)),
    }
}

/// Python's syntax error message for one SQL string, None where it parses; raises where Python
/// raises: `ValueError` for SQL the analysis normalization rejects or an unknown dialect.
#[pyfunction]
#[pyo3(signature = (sql, placeholders, dialect, parse_one=false))]
fn sql_syntax_error(
    py: Python<'_>,
    sql: String,
    placeholders: Option<HashMap<String, String>>,
    dialect: Option<String>,
    parse_one: bool,
) -> PyResult<Option<String>> {
    let check = SyntaxCheck {
        sql,
        placeholders: placeholders.unwrap_or_default().into_iter().collect(),
    };
    let dialect: String = dialect
        .filter(|dialect| !dialect.is_empty())
        .unwrap_or_else(|| "generic".to_owned());
    let mode = if parse_one {
        SyntaxMode::Parse
    } else {
        SyntaxMode::Validate
    };
    py.compiler_detach(|| Ok(check_syntax_error(&check, &dialect, mode)))
        .map_err(compiler_error)?
        .map_err(|failure| match failure {
            SyntaxFailure::Normalization(message) => PyValueError::new_err(message),
            SyntaxFailure::UnknownDialect(name) => {
                PyValueError::new_err(format!("Unknown dialect: {name}"))
            }
        })
}

/// Whether every `(sql, placeholders)` parses, or None with the reason Python must check it.
#[pyfunction]
fn check_native_sql_syntax(
    py: Python<'_>,
    request: (String, Vec<(String, Pairs)>),
) -> (Option<bool>, Option<String>) {
    let (dialect, rows) = request;
    let checks: Vec<SyntaxCheck> = rows
        .into_iter()
        .map(|(sql, placeholders)| SyntaxCheck { sql, placeholders })
        .collect();
    match py.compiler_detach(|| check_sql_syntax(&dialect, &checks)) {
        Ok(valid) => (Some(valid), None),
        Err(reason) => (None, Some(reason)),
    }
}

fn project_request(request: RequestRow) -> ProjectRequest {
    let (
        dialect,
        target,
        defaults,
        variables,
        environment,
        models,
        sources,
        seeds,
        functions,
        audits,
    ) = request;
    let (database, schema, seed_database, seed_schema) = defaults;
    ProjectRequest {
        dialect,
        target: target.map(|(database, schema, loader_schema)| TargetNamespace {
            database,
            schema,
            loader_schema,
        }),
        defaults: SeedDefaults {
            database,
            schema,
            seed_database,
            seed_schema,
        },
        variables: variables.into_iter().map(variable).collect(),
        environment,
        models: models.into_iter().map(model).collect(),
        sources: sources
            .into_iter()
            .map(|(name, managed, database, schema)| SourceFacts {
                name,
                managed,
                database,
                schema,
            })
            .collect(),
        seeds: seeds
            .into_iter()
            .map(|(name, database, schema)| SeedFacts {
                name,
                database,
                schema,
            })
            .collect(),
        functions: functions.into_iter().map(references).collect(),
        audits: audits
            .into_iter()
            .map(|(rows, attached)| AuditFacts {
                references: references(rows),
                attached,
            })
            .collect(),
    }
}

fn variable(row: VariableRow) -> (String, Variable) {
    let (name, kind, text) = row;
    let value: Variable = match kind.as_str() {
        TEXT_VARIABLE => Variable::Scalar(Scalar::Text(text)),
        BOOLEAN_VARIABLE => Variable::Scalar(Scalar::Bool(text == TRUE_TEXT)),
        NONE_VARIABLE => Variable::Scalar(Scalar::Null),
        _ => Variable::Unsupported,
    };
    (name, value)
}

fn model(row: ModelRow) -> ModelFacts {
    let (rows, checks) = row;
    ModelFacts {
        references: references(rows),
        syntax_checks: checks
            .into_iter()
            .map(|(sql, placeholders)| SyntaxCheck { sql, placeholders })
            .collect(),
    }
}

fn references(rows: Vec<ReferenceRow>) -> Vec<Reference> {
    rows.into_iter()
        .map(|(kind, name, package)| Reference {
            kind,
            name,
            package,
        })
        .collect()
}

fn resources_row(resources: ProjectResources) -> ResourcesRow {
    (
        resources.model_deps,
        resources.sources,
        resources.seeds.into_iter().map(namespace_row).collect(),
        resources.function_deps,
        resources.audit_deps,
        resources.reads.into_iter().map(read_row).collect(),
        resources.model_syntax_valid,
    )
}

fn read_row(read: InputRead) -> (&'static str, String) {
    match read {
        InputRead::Environment(name) => (ENVIRONMENT_READ, name),
        InputRead::Context(name) => (CONTEXT_READ, name),
    }
}

fn namespace_row(namespace: Namespace) -> NamespaceRow {
    (
        namespace.database,
        namespace.schema,
        namespace.logical_database,
        namespace.logical_schema,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(assemble_project_resource_facts, module)?)?;
    module.add_function(wrap_pyfunction!(check_native_sql_syntax, module)?)?;
    module.add_function(wrap_pyfunction!(sql_syntax_error, module)?)?;
    Ok(())
}
