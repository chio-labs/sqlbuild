//! Native discovery results as the plain data the Python discovery facade materialises.

use pyo3::prelude::{Bound, IntoPyObject, Py, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyTuple;
use pyo3::{IntoPyObjectExt, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_core::text::main::python_text::python_text;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_discovery::declarations::main::declaration_layout::declaration_layout;
use sqlbuild_discovery::declarations::models::{
    DeclarationFileFact, DeclarationGroup, DeclarationLayout,
};
use sqlbuild_discovery::model_files::main::discover_model_files::discover_model_files as discover_models;
use sqlbuild_discovery::model_files::models::{DiscoveredModelFile, ModelFileOptions};
use sqlbuild_discovery::models::{
    DiscoveredFile, DiscoveryFailure, FileOutcome, LineColumnSpan, ProjectRoot, StageDeferral,
};
use sqlbuild_discovery::sql_tests::main::discover_scenario_files::discover_scenario_files as discover_scenarios;
use sqlbuild_discovery::sql_tests::main::discover_sql_test_files::discover_sql_test_files as discover_tests;
use sqlbuild_discovery::sql_tests::models::{
    DiscoveredScenarioFile, DiscoveredSqlTestFile, SqlTestBlock, SqlTestFileOptions,
};
use sqlbuild_discovery::tree::main::listings::read_listings;
use sqlbuild_discovery::tree::models::{ProjectTree, TreeEntry};
use sqlbuild_discovery::yaml_files::main::load_yaml_files::load_yaml_files as load_yaml;
use sqlbuild_discovery::yaml_files::models::YamlFileOutcome;
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use crate::bindings::_helpers::boundary::config_values::config_value_to_python;
use crate::bindings::_helpers::sqltext::authored_values::map_to_python;
use crate::bindings::models::{ModelDiscoveryRequest, NativeProjectTree, SqlTestDiscoveryRequest};
use crate::bindings::types::CompilerDetach;

type PyObject = Py<PyAny>;
type Located = (String, usize, usize, usize, usize);

fn located(locations: Vec<(String, LineColumnSpan)>) -> Vec<Located> {
    locations
        .into_iter()
        .map(|(name, span)| (name, span.line, span.column, span.end_line, span.end_column))
        .collect()
}

fn tuple_object<'py>(py: Python<'py>, items: Vec<PyObject>) -> PyResult<PyObject> {
    Ok(PyTuple::new(py, items)?.unbind().into_any())
}

fn object<'py, T: IntoPyObject<'py>>(py: Python<'py>, value: T) -> PyResult<PyObject> {
    value.into_py_any(py)
}

fn outcome_object<T>(
    py: Python<'_>,
    outcome: FileOutcome<T>,
    parsed: impl FnOnce(Python<'_>, T) -> PyResult<PyObject>,
) -> PyResult<PyObject> {
    match outcome {
        FileOutcome::Parsed(value) => parsed(py, value),
        FileOutcome::Unreadable => tuple_object(py, vec![object(py, "read")?]),
        FileOutcome::Failed(failure) => failure_object(py, failure),
    }
}

fn model_object(py: Python<'_>, model: DiscoveredModelFile) -> PyResult<PyObject> {
    tuple_object(
        py,
        vec![
            object(py, "ok")?,
            object(py, model.contents)?,
            map_to_python(py, model.header_values)?,
            object(py, located(model.header_column_locations))?,
            object(py, located(model.output_column_locations))?,
            object(py, model.query_sql)?,
        ],
    )
}

fn files_object<T>(
    py: Python<'_>,
    files: Vec<DiscoveredFile<T>>,
    parsed: impl Fn(Python<'_>, T) -> PyResult<PyObject>,
) -> PyResult<Vec<(String, PyObject)>> {
    files
        .into_iter()
        .map(|file| {
            Ok((
                file.relative_path,
                outcome_object(py, file.outcome, &parsed)?,
            ))
        })
        .collect()
}

type Listing = (String, Vec<(String, bool, bool)>);
type FactRow = (
    String,
    &'static str,
    &'static str,
    String,
    Option<String>,
    String,
);
type DeclarationLayoutRows = (Option<Vec<FactRow>>, Option<Vec<(String, String)>>);

fn entry_rows(entries: &[TreeEntry]) -> Vec<(String, bool, bool)> {
    entries
        .iter()
        .map(|entry| (entry.name.clone(), entry.is_dir, entry.is_walkable_dir))
        .collect()
}

fn fact_row(fact: DeclarationFileFact) -> FactRow {
    (
        fact.relative_path,
        fact.kind.as_str(),
        fact.scope_kind.as_str(),
        fact.ownership_root,
        fact.owning_path,
        fact.declaration_root,
    )
}

fn group_row(group: DeclarationGroup) -> (String, String) {
    (group.root, group.directory)
}

fn valid_rows<T, R>(outcome: Result<Vec<T>, DiscoveryFailure>, row: fn(T) -> R) -> Option<Vec<R>> {
    match outcome {
        Ok(items) => Some(items.into_iter().map(row).collect()),
        Err(_failure) => None,
    }
}

#[pymethods]
impl NativeProjectTree {
    #[new]
    fn new(project_dir: &str) -> Self {
        Self {
            inner: ProjectTree::new(Path::new(project_dir)),
            exported: Mutex::new(HashSet::new()),
        }
    }

    /// The listings read since the last call, for the pass's Python directory snapshot.
    fn listings(&self) -> Vec<Listing> {
        let Ok(mut exported) = self.exported.lock() else {
            return Vec::new();
        };
        read_listings(&self.inner)
            .into_iter()
            .filter(|(directory, _)| exported.insert(directory.clone()))
            .map(|(directory, entries)| (directory, entry_rows(&entries)))
            .collect()
    }
}

/// Discover the model files natively, or return `None` when Python must run the stage.
#[pyfunction]
fn discover_model_files(
    py: Python<'_>,
    request: ModelDiscoveryRequest,
    tree: &NativeProjectTree,
) -> PyResult<Option<Vec<(String, PyObject)>>> {
    let Some(python) = python_text(request.python_version, &request.unicode_version) else {
        return Ok(None);
    };
    let root = ProjectRoot {
        directory: PathBuf::from(request.project_dir),
        display_prefix: request.display_prefix,
    };
    let options = ModelFileOptions {
        supported_keys: request.supported_keys,
        removed_keys: request.removed_keys,
        extract_implicit_alias_columns: request.extract_implicit_alias_columns,
        extract_output_column_locations: request.extract_output_column_locations,
        python,
    };
    let discovered: Result<Vec<DiscoveredFile<DiscoveredModelFile>>, StageDeferral> = py
        .compiler_detach(|| Ok(discover_models(&root, &tree.inner, &options)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    match discovered {
        Ok(files) => Ok(Some(files_object(py, files, model_object)?)),
        Err(_deferral) => Ok(None),
    }
}

/// The valid declaration file facts and named declaration groups; `None` where Python must scan.
#[pyfunction]
fn discover_declaration_layout(
    py: Python<'_>,
    tree: &NativeProjectTree,
) -> PyResult<Option<DeclarationLayoutRows>> {
    let layout: Result<DeclarationLayout, StageDeferral> = py
        .compiler_detach(|| Ok(declaration_layout(&tree.inner)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    match layout {
        Ok(layout) => Ok(Some((
            valid_rows(layout.file_facts, fact_row),
            valid_rows(layout.named_groups, group_row),
        ))),
        Err(_deferral) => Ok(None),
    }
}

fn failure_object(py: Python<'_>, failure: DiscoveryFailure) -> PyResult<PyObject> {
    tuple_object(
        py,
        vec![
            object(py, "error")?,
            object(py, failure.kind.as_str())?,
            object(py, failure.message)?,
            object(py, failure.help)?,
        ],
    )
}

fn test_block_object(py: Python<'_>, block: SqlTestBlock) -> PyResult<PyObject> {
    tuple_object(
        py,
        vec![
            map_to_python(py, block.header_values)?,
            object(py, block.sql_body)?,
        ],
    )
}

fn test_file_object(py: Python<'_>, file: DiscoveredSqlTestFile) -> PyResult<PyObject> {
    let blocks: Vec<PyObject> = file
        .blocks
        .into_iter()
        .map(|block| test_block_object(py, block))
        .collect::<PyResult<_>>()?;
    let failure: Option<PyObject> = file
        .failure
        .map(|failure| failure_object(py, failure))
        .transpose()?;
    tuple_object(
        py,
        vec![
            object(py, "ok")?,
            object(py, file.contents)?,
            object(py, blocks)?,
            object(py, failure)?,
        ],
    )
}

fn scenario_object(py: Python<'_>, file: DiscoveredScenarioFile) -> PyResult<PyObject> {
    tuple_object(
        py,
        vec![
            object(py, "ok")?,
            object(py, file.contents)?,
            map_to_python(py, file.header_values)?,
            object(py, file.sql_body)?,
        ],
    )
}

/// The root and options of one request, or `None` when native cannot reproduce this Python.
fn sql_test_inputs(request: SqlTestDiscoveryRequest) -> Option<(ProjectRoot, SqlTestFileOptions)> {
    let python: PythonText = python_text(request.python_version, &request.unicode_version)?;
    Some((
        ProjectRoot {
            directory: PathBuf::from(request.project_dir),
            display_prefix: request.display_prefix,
        },
        SqlTestFileOptions {
            test_keys: request.test_keys,
            scenario_keys: request.scenario_keys,
            python,
        },
    ))
}

/// Discover and split the SQL test files natively, or return `None` when Python must run.
#[pyfunction]
fn discover_sql_test_files(
    py: Python<'_>,
    request: SqlTestDiscoveryRequest,
    tree: &NativeProjectTree,
) -> PyResult<Option<Vec<(String, PyObject)>>> {
    let Some((root, options)) = sql_test_inputs(request) else {
        return Ok(None);
    };
    let discovered: Result<Vec<DiscoveredFile<DiscoveredSqlTestFile>>, StageDeferral> = py
        .compiler_detach(|| Ok(discover_tests(&root, &tree.inner, &options)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    match discovered {
        Ok(files) => Ok(Some(files_object(py, files, test_file_object)?)),
        Err(_deferral) => Ok(None),
    }
}

/// Discover and header-parse the scenario files natively, or return `None` when Python must run.
#[pyfunction]
fn discover_scenario_files(
    py: Python<'_>,
    request: SqlTestDiscoveryRequest,
    tree: &NativeProjectTree,
) -> PyResult<Option<Vec<(String, PyObject)>>> {
    let Some((root, options)) = sql_test_inputs(request) else {
        return Ok(None);
    };
    let discovered: Result<Vec<DiscoveredFile<DiscoveredScenarioFile>>, StageDeferral> = py
        .compiler_detach(|| Ok(discover_scenarios(&root, &tree.inner, &options)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    match discovered {
        Ok(files) => Ok(Some(files_object(py, files, scenario_object)?)),
        Err(_deferral) => Ok(None),
    }
}

/// One file's payload; a value Python cannot hold natively makes Python load that file.
fn yaml_file_object(py: Python<'_>, outcome: YamlFileOutcome) -> PyResult<PyObject> {
    match outcome {
        YamlFileOutcome::Loaded { contents, value } => match config_value_to_python(py, value) {
            Ok(loaded) => tuple_object(py, vec![object(py, "ok")?, object(py, contents)?, loaded]),
            Err(_unconvertible) => {
                tuple_object(py, vec![object(py, "load")?, object(py, contents)?])
            }
        },
        YamlFileOutcome::LoadInPython { contents } => {
            tuple_object(py, vec![object(py, "load")?, object(py, contents)?])
        }
        YamlFileOutcome::Unreadable => tuple_object(py, vec![object(py, "read")?]),
    }
}

/// Read and load YAML files natively, one payload per path, or `None` when Python must run.
#[pyfunction]
fn load_yaml_files(
    py: Python<'_>,
    relative_paths: Vec<String>,
    tree: &NativeProjectTree,
) -> PyResult<Option<Vec<PyObject>>> {
    let loaded: Result<Vec<YamlFileOutcome>, StageDeferral> = py
        .compiler_detach(|| Ok(load_yaml(&tree.inner, &relative_paths)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    match loaded {
        Ok(outcomes) => Ok(Some(
            outcomes
                .into_iter()
                .map(|outcome| yaml_file_object(py, outcome))
                .collect::<PyResult<_>>()?,
        )),
        Err(_deferral) => Ok(None),
    }
}

/// Whether native discovery reproduces the string semantics of this Python and Unicode version.
#[pyfunction]
fn native_text_supported(python_version: (u8, u8), unicode_version: &str) -> bool {
    python_text(python_version, unicode_version).is_some()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(native_text_supported, module)?)?;
    module.add_function(wrap_pyfunction!(load_yaml_files, module)?)?;
    module.add_function(wrap_pyfunction!(discover_sql_test_files, module)?)?;
    module.add_function(wrap_pyfunction!(discover_scenario_files, module)?)?;
    module.add_class::<NativeProjectTree>()?;
    module.add_function(wrap_pyfunction!(discover_model_files, module)?)?;
    module.add_function(wrap_pyfunction!(discover_declaration_layout, module)?)?;
    Ok(())
}
