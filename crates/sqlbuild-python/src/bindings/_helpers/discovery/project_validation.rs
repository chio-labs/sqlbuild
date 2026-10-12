//! Cross-file validation of one discovery's inputs, from the facts the Python facade lists.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{FromPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_discovery::project_validation::main::validate_project_inputs::validate_project_inputs;
use sqlbuild_discovery::project_validation::models::{
    AuditFileFact, CsvSettings, DependencyFact, IntegrationLoaderFact, ModelFact, NamedPath,
    NodeFact, NodeKind, ProjectFacts, SchemaFileFact, ScopedDeclarationsFact, SeedEntryFact,
    SeedFileFact, SourceFact, SourceFileFact, TestBlockFact, TestFileFact, ValidationFailure,
};

use crate::bindings::_helpers::discovery::project_files::{
    PyObject, failure_object, object, read_object, tuple_object,
};

const CSV_ERROR_TAG: &str = "csv";
const CSV_SETTING_TAG: &str = "csv_setting";
const UNREADABLE_TAG: &str = "unreadable";

type Pair = (String, String);
/// `(stem, path, blocks)` of a SQL test file; a block is `(name, case names)`.
type TestFileRow = (String, String, Vec<(Option<String>, Vec<String>)>);

#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct SeedEntryRow {
    name: String,
    columns: Vec<String>,
    delimiter: Option<String>,
    quotechar: Option<String>,
    escapechar: Option<String>,
    doublequote: Option<bool>,
    skipinitialspace: Option<bool>,
}

#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct SourceRow {
    name: String,
    managed: bool,
    loader: Option<String>,
    integration_kind: Option<String>,
}

#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct NodeRow {
    kind: String,
    name: String,
    path: String,
    decorator_config: bool,
    /// `(SQL resource name, owning node index, decorated name)` per dependency.
    depends_on: Vec<(Option<String>, Option<usize>, Option<String>)>,
}

#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct FactRows {
    models: Vec<(String, String, Vec<Pair>)>,
    sql_functions: Vec<Pair>,
    python_functions: Vec<Pair>,
    sql_hooks: Vec<Pair>,
    seeds: Vec<(String, String, String)>,
    schemas: Vec<(String, Vec<String>, Vec<SeedEntryRow>)>,
    sources: Vec<(String, Vec<SourceRow>)>,
    tests: Vec<TestFileRow>,
    scenarios: Vec<Pair>,
    audits: Vec<(Pair, bool, Vec<Option<String>>)>,
    declaration_files: Vec<(bool, Vec<Pair>)>,
    model_schemas: Vec<Pair>,
    materializations: Vec<Pair>,
    nodes: Vec<NodeRow>,
    hook_functions: Vec<Pair>,
    event_exporters: Vec<Pair>,
    providers: Vec<Pair>,
    path_default_keys: Vec<String>,
}

fn named((name, path): Pair) -> NamedPath {
    NamedPath { name, path }
}

fn all_named(rows: Vec<Pair>) -> Vec<NamedPath> {
    rows.into_iter().map(named).collect()
}

fn node_kind(kind: &str) -> PyResult<NodeKind> {
    match kind {
        "loader" => Ok(NodeKind::Loader),
        "task" => Ok(NodeKind::Task),
        "asset" => Ok(NodeKind::Asset),
        "check" => Ok(NodeKind::Check),
        other => Err(pyo3::exceptions::PyValueError::new_err(format!(
            "unknown Python node kind {other:?}"
        ))),
    }
}

fn project_facts(rows: FactRows) -> PyResult<ProjectFacts> {
    let nodes: Vec<NodeFact> = rows
        .nodes
        .into_iter()
        .map(|node| {
            Ok(NodeFact {
                kind: node_kind(&node.kind)?,
                name: node.name,
                path: node.path,
                decorator_config: node.decorator_config,
                depends_on: node
                    .depends_on
                    .into_iter()
                    .map(|(sql_name, owner, decorated_name)| match sql_name {
                        Some(name) => DependencyFact::SqlResource { name },
                        None => DependencyFact::Object {
                            owner,
                            decorated_name,
                        },
                    })
                    .collect(),
            })
        })
        .collect::<PyResult<_>>()?;
    Ok(ProjectFacts {
        models: rows
            .models
            .into_iter()
            .map(|(name, path, local)| ModelFact {
                file: NamedPath { name, path },
                local_declarations: all_named(local),
            })
            .collect(),
        sql_functions: all_named(rows.sql_functions),
        python_functions: all_named(rows.python_functions),
        sql_hooks: all_named(rows.sql_hooks),
        seeds: rows
            .seeds
            .into_iter()
            .map(|(name, path, absolute_path)| SeedFileFact {
                file: NamedPath { name, path },
                absolute_path,
            })
            .collect(),
        schemas: rows
            .schemas
            .into_iter()
            .map(|(path, model_names, seeds)| SchemaFileFact {
                path,
                model_names,
                seeds: seeds
                    .into_iter()
                    .map(|seed| SeedEntryFact {
                        name: seed.name,
                        columns: seed.columns,
                        csv: CsvSettings {
                            delimiter: seed.delimiter,
                            quotechar: seed.quotechar,
                            escapechar: seed.escapechar,
                            doublequote: seed.doublequote,
                            skipinitialspace: seed.skipinitialspace,
                        },
                    })
                    .collect(),
            })
            .collect(),
        sources: rows
            .sources
            .into_iter()
            .map(|(path, entries)| SourceFileFact {
                path,
                entries: entries
                    .into_iter()
                    .map(|entry| SourceFact {
                        name: entry.name,
                        managed: entry.managed,
                        loader: entry.loader,
                        integration_loader: entry
                            .integration_kind
                            .map(|kind| IntegrationLoaderFact { kind }),
                    })
                    .collect(),
            })
            .collect(),
        tests: rows
            .tests
            .into_iter()
            .map(|(name, path, blocks)| TestFileFact {
                file: NamedPath { name, path },
                blocks: blocks
                    .into_iter()
                    .map(|(name, cases)| TestBlockFact { name, cases })
                    .collect(),
            })
            .collect(),
        scenarios: all_named(rows.scenarios),
        audits: rows
            .audits
            .into_iter()
            .map(|(file, generic, block_names)| AuditFileFact {
                file: named(file),
                generic,
                block_names,
            })
            .collect(),
        declaration_files: rows
            .declaration_files
            .into_iter()
            .map(|(private, declarations)| ScopedDeclarationsFact {
                private,
                declarations: all_named(declarations),
            })
            .collect(),
        model_schemas: all_named(rows.model_schemas),
        materializations: all_named(rows.materializations),
        nodes,
        hook_functions: all_named(rows.hook_functions),
        event_exporters: all_named(rows.event_exporters),
        providers: all_named(rows.providers),
        path_default_keys: rows.path_default_keys,
    })
}

/// `None` when the inputs are consistent, else the payload of the first error Python raises.
#[pyfunction]
fn validate_discovered_inputs(py: Python<'_>, rows: FactRows) -> PyResult<Option<PyObject>> {
    let facts: ProjectFacts = project_facts(rows)?;
    let failure: ValidationFailure = match validate_project_inputs(&facts) {
        Ok(()) => return Ok(None),
        Err(failure) => failure,
    };
    let payload: PyObject = match failure {
        ValidationFailure::Discovery(failure) => failure_object(py, failure)?,
        ValidationFailure::Unreadable {
            absolute_path,
            failure,
        } => tuple_object(
            py,
            vec![
                object(py, UNREADABLE_TAG)?,
                object(py, absolute_path)?,
                read_object(py, failure)?,
            ],
        )?,
        ValidationFailure::Csv(message) => {
            tuple_object(py, vec![object(py, CSV_ERROR_TAG)?, object(py, message)?])?
        }
        ValidationFailure::CsvSetting(message) => {
            tuple_object(py, vec![object(py, CSV_SETTING_TAG)?, object(py, message)?])?
        }
    };
    Ok(Some(payload))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(validate_discovered_inputs, module)?)
}
