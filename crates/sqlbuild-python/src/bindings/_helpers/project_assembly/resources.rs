//! Python's resource assembly facts for one project, computed natively for the preview engine.

use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyString, PyStringMethods};
use pyo3::{PyErr, pyfunction, wrap_pyfunction};
use sqlbuild_analysis::assembly::analysis_session::types::Pairs;
use sqlbuild_analysis::assembly::project::errors::AssemblyError;
use sqlbuild_analysis::assembly::project::main::assemble_project_resources::assemble_project_resources;
use sqlbuild_analysis::assembly::project::main::check_sql_syntax::check_sql_syntax;
use sqlbuild_analysis::assembly::project::main::environment_template_names::environment_template_names as template_names;
use sqlbuild_analysis::assembly::project::main::sql_syntax_error::sql_syntax_error as check_syntax_error;
use sqlbuild_analysis::assembly::project::models::{
    AuditFacts, FunctionFacts, InputRead, ModelFacts, Namespace, OpaqueRender, OpaqueVariable,
    ProjectRequest, ProjectResources, Reference, ResourceFailure, ResourceSlot, SeedDefaults,
    SeedFacts, SourceFacts, SyntaxCheck, SyntaxFailure, SyntaxMode, TargetNamespace, Variable,
};
use sqlbuild_analysis::assembly::project::types::ObjectKey;
use sqlbuild_core::panics::main::native_failure::native_failure;
use sqlbuild_model_config::templates::models::Scalar;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

const PROJECT_ASSEMBLY_CONTEXT: &str = "native project assembly";
const SYNTAX_CHECK_CONTEXT: &str = "native SQL syntax check";

const TEXT_VARIABLE: &str = "text";
const BOOLEAN_VARIABLE: &str = "bool";
const NONE_VARIABLE: &str = "none";
const OPAQUE_VARIABLE: &str = "opaque";
const RENDERED_TEXT: &str = "text";
const RENDER_REJECTED: &str = "rejected";
const RENDER_RAISES: &str = "raises";
const SOURCE_SLOT: &str = "source";
const SEED_SLOT: &str = "seed";
const AUDIT_SLOT: &str = "audit";
const COMPILE_INPUT_ERROR: &str = "compile_input";
const VALUE_ERROR: &str = "value";
const HELD_ERROR: &str = "held";
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
/// `(name, kind, text, render)`: kind `text`, `bool`, `none` or `opaque` with a render pair.
type VariableRow = (String, String, String, Option<(String, String)>);
/// `(resource list, index, error class, message, help, held exception index)`.
type FailureRow = (
    &'static str,
    usize,
    &'static str,
    String,
    Option<String>,
    Option<usize>,
);
/// `(name, directory, tags, references, [(sql, placeholders)])`.
type ModelRow = (
    String,
    String,
    Vec<String>,
    Vec<ReferenceRow>,
    Vec<(String, Pairs)>,
);
/// `(name, managed, database, schema)`.
type SourceRow = (String, bool, Option<String>, Option<String>);
/// `(name, tags, database, schema)`.
type SeedRow = (String, Vec<String>, Option<String>, Option<String>);
/// `(kind, name, tags, references)`.
type FunctionRow = (String, String, Vec<String>, Vec<ReferenceRow>);
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
    Vec<FunctionRow>,
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
    Option<FailureRow>,
);

/// The project's resource facts up to the resource Python's assembly raises at.
#[pyfunction]
fn assemble_project_resource_facts(py: Python<'_>, request: RequestRow) -> PyResult<ResourcesRow> {
    let request: ProjectRequest = project_request(request)?;
    let resources: ProjectResources = py
        .compiler_detach(|| assemble_project_resources(&request))
        .map_err(|reason| compiler_error(native_failure(PROJECT_ASSEMBLY_CONTEXT, &reason)))?;
    resources_row(resources)
}

/// Python's syntax error message for one SQL string, None where it parses.
#[pyfunction]
#[pyo3(signature = (sql, placeholders, dialect, parse_one=false))]
fn sql_syntax_error(
    sql: &Bound<'_, PyString>,
    placeholders: Option<HashMap<String, String>>,
    dialect: Option<String>,
    parse_one: bool,
) -> PyResult<Option<String>> {
    let py: Python<'_> = sql.py();
    let check = SyntaxCheck {
        sql: sql.to_str()?.to_owned(),
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
    syntax_error_message(py, &check, &dialect, mode)
}

/// Python's syntax error message for one check, raising what Python's validation raises.
pub(crate) fn syntax_error_message(
    py: Python<'_>,
    check: &SyntaxCheck,
    dialect: &str,
    mode: SyntaxMode,
) -> PyResult<Option<String>> {
    py.compiler_detach(|| Ok(check_syntax_error(check, dialect, mode)))
        .map_err(compiler_error)?
        .map_err(syntax_value_error)
}

/// The `ValueError` Python's syntax validation raises before parsing.
fn syntax_value_error(failure: SyntaxFailure) -> PyErr {
    match failure {
        SyntaxFailure::Normalization(message) => PyValueError::new_err(message),
        SyntaxFailure::UnknownDialect(name) => {
            PyValueError::new_err(format!("Unknown dialect: {name}"))
        }
    }
}

/// Whether every `(sql, placeholders)` parses, raising the `ValueError` Python's validation raises.
#[pyfunction]
fn check_native_sql_syntax(
    py: Python<'_>,
    request: (String, Vec<(String, Pairs)>),
) -> PyResult<bool> {
    let (dialect, rows) = request;
    let checks: Vec<SyntaxCheck> = rows
        .into_iter()
        .map(|(sql, placeholders)| SyntaxCheck { sql, placeholders })
        .collect();
    syntax_valid(py, &dialect, &checks)
}

/// Whether every check parses, raising what Python's validation raises.
pub(crate) fn syntax_valid(
    py: Python<'_>,
    dialect: &str,
    checks: &[SyntaxCheck],
) -> PyResult<bool> {
    py.compiler_detach(|| check_sql_syntax(dialect, checks))
        .map_err(|reason| compiler_error(native_failure(SYNTAX_CHECK_CONTEXT, &reason)))?
        .map_err(syntax_value_error)
}

fn project_request(request: RequestRow) -> PyResult<ProjectRequest> {
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
    Ok(ProjectRequest {
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
        variables: variables
            .into_iter()
            .map(variable)
            .collect::<PyResult<_>>()?,
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
            .map(|(name, tags, database, schema)| SeedFacts {
                name,
                tags,
                database,
                schema,
            })
            .collect(),
        functions: functions
            .into_iter()
            .map(|(kind, name, tags, rows)| FunctionFacts {
                kind,
                name,
                tags,
                references: references(rows),
            })
            .collect(),
        audits: audits
            .into_iter()
            .map(|(rows, attached)| AuditFacts {
                references: references(rows),
                attached,
            })
            .collect(),
    })
}

fn variable(row: VariableRow) -> PyResult<(String, Variable)> {
    let (name, kind, text, render) = row;
    let value: Variable = match (kind.as_str(), render) {
        (TEXT_VARIABLE, _) => Variable::Scalar(Scalar::Text(text)),
        (BOOLEAN_VARIABLE, _) => Variable::Scalar(Scalar::Bool(text == TRUE_TEXT)),
        (NONE_VARIABLE, _) => Variable::Scalar(Scalar::Null),
        (OPAQUE_VARIABLE, Some((render_kind, payload))) => Variable::Opaque(OpaqueVariable {
            text,
            render: opaque_render(&render_kind, payload)?,
        }),
        _ => {
            return Err(compiler_error(native_failure(
                PROJECT_ASSEMBLY_CONTEXT,
                &format!("an unknown variable kind '{kind}'"),
            )));
        }
    };
    Ok((name, value))
}

fn opaque_render(kind: &str, payload: String) -> PyResult<OpaqueRender> {
    match kind {
        RENDERED_TEXT => Ok(OpaqueRender::Text(payload)),
        RENDER_REJECTED => Ok(OpaqueRender::Rejected(payload)),
        RENDER_RAISES => payload.parse().map(OpaqueRender::Raises).map_err(|_| {
            compiler_error(native_failure(
                PROJECT_ASSEMBLY_CONTEXT,
                "an opaque variable's held exception index is not a number",
            ))
        }),
        _ => Err(compiler_error(native_failure(
            PROJECT_ASSEMBLY_CONTEXT,
            &format!("an unknown variable rendering '{kind}'"),
        ))),
    }
}

fn model(row: ModelRow) -> ModelFacts {
    let (name, directory, tags, rows, checks) = row;
    ModelFacts {
        name,
        directory,
        tags,
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

fn resources_row(resources: ProjectResources) -> PyResult<ResourcesRow> {
    let failure: Option<FailureRow> = resources.failure.map(failure_row).transpose()?;
    Ok((
        resources.model_deps,
        resources.sources,
        resources.seeds.into_iter().map(namespace_row).collect(),
        resources.function_deps,
        resources.audit_deps,
        resources.reads.into_iter().map(read_row).collect(),
        resources.model_syntax_valid,
        failure,
    ))
}

/// `(resource list, index, error class, message, help, held exception index)`.
fn failure_row(failure: ResourceFailure) -> PyResult<FailureRow> {
    let slot: &'static str = match failure.slot {
        ResourceSlot::Source => SOURCE_SLOT,
        ResourceSlot::Seed => SEED_SLOT,
        ResourceSlot::Audit => AUDIT_SLOT,
    };
    Ok(match failure.error {
        AssemblyError::CompileInput { message, help } => (
            slot,
            failure.index,
            COMPILE_INPUT_ERROR,
            message,
            help,
            None,
        ),
        AssemblyError::Value(message) => (slot, failure.index, VALUE_ERROR, message, None, None),
        AssemblyError::Raise(held) => (
            slot,
            failure.index,
            HELD_ERROR,
            String::new(),
            None,
            Some(held),
        ),
        AssemblyError::Internal(reason) => {
            return Err(compiler_error(native_failure(
                PROJECT_ASSEMBLY_CONTEXT,
                &reason,
            )));
        }
    })
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

/// The distinct `ENV:` names target templates read, in first-seen order.
#[pyfunction]
fn environment_template_names(values: Vec<Option<String>>) -> Vec<String> {
    template_names(&values)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(assemble_project_resource_facts, module)?)?;
    module.add_function(wrap_pyfunction!(check_native_sql_syntax, module)?)?;
    module.add_function(wrap_pyfunction!(sql_syntax_error, module)?)?;
    module.add_function(wrap_pyfunction!(environment_template_names, module)?)?;
    Ok(())
}
