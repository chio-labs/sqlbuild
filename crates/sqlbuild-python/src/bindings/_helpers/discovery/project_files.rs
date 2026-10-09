//! Native discovery results as the plain data the Python discovery facade materialises.

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::{Bound, IntoPyObject, Py, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBytes, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_core::text::main::python_text::python_text;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_discovery::declarations::main::declaration_layout::declaration_layout;
use sqlbuild_discovery::declarations::models::{
    DeclarationFileFact, DeclarationGroup, DeclarationKind, DeclarationLayout,
};
use sqlbuild_discovery::model_files::main::discover_model_files::discover_model_files as discover_models;
use sqlbuild_discovery::model_files::main::parse_model_text::parse_model_text;
use sqlbuild_discovery::model_files::models::{DiscoveredModelFile, ModelFileOptions};
use sqlbuild_discovery::models::{
    DiscoveredFile, DiscoveryFailure, FailureKind, FileOutcome, LineColumnSpan, ProjectRoot,
    ReadFailure, StageFailure,
};
use sqlbuild_discovery::sql_tests::main::discover_scenario_files::discover_scenario_files as discover_scenarios;
use sqlbuild_discovery::sql_tests::main::discover_sql_test_files::discover_sql_test_files as discover_tests;
use sqlbuild_discovery::sql_tests::main::parse_scenario_text::parse_scenario_text;
use sqlbuild_discovery::sql_tests::main::parse_sql_test_text::parse_sql_test_text;
use sqlbuild_discovery::sql_tests::models::{
    DiscoveredScenarioFile, DiscoveredSqlTestFile, SqlTestBlock, SqlTestFileOptions,
};
use sqlbuild_discovery::tree::main::listings::read_listings;
use sqlbuild_discovery::tree::models::{ProjectTree, TreeEntry};
use sqlbuild_discovery::yaml_files::main::load_yaml_files::load_yaml_files as load_yaml;
use sqlbuild_discovery::yaml_files::main::load_yaml_text::load_yaml_text;
use sqlbuild_discovery::yaml_files::models::YamlFileOutcome;
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use crate::bindings::_helpers::boundary::config_values::config_value_to_python;
use crate::bindings::_helpers::sqltext::authored_values::map_to_python;
use crate::bindings::models::{
    ModelDiscoveryRequest, ModelTextRequest, NativeProjectTree, SqlTestDiscoveryRequest,
    SqlTestTextRequest, YamlDiscoveryRequest,
};
use crate::bindings::types::CompilerDetach;

pub(crate) type PyObject = Py<PyAny>;
type Located = (String, usize, usize, usize, usize);
type Listing = (PyObject, Vec<(PyObject, bool, bool)>);

fn located(locations: Vec<(String, LineColumnSpan)>) -> Vec<Located> {
    locations
        .into_iter()
        .map(|(name, span)| (name, span.line, span.column, span.end_line, span.end_column))
        .collect()
}

pub(crate) fn tuple_object<'py>(py: Python<'py>, items: Vec<PyObject>) -> PyResult<PyObject> {
    Ok(PyTuple::new(py, items)?.unbind().into_any())
}

pub(crate) fn object<'py, T: IntoPyObject<'py>>(py: Python<'py>, value: T) -> PyResult<PyObject> {
    value.into_py_any(py)
}

/// The Python semantics native parsing reproduces; an unknown Python is rejected by the facade.
pub(crate) fn python_semantics(
    python_version: (u8, u8),
    unicode_version: &str,
) -> PyResult<PythonText> {
    python_text(python_version, unicode_version).ok_or_else(|| {
        PyValueError::new_err(format!(
            "native discovery does not support Python {}.{} with Unicode {unicode_version}",
            python_version.0, python_version.1
        ))
    })
}

pub(crate) fn failure_object(py: Python<'_>, failure: DiscoveryFailure) -> PyResult<PyObject> {
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

/// `("read", "os", errno, message, winerror)` or `("read", "decode", bytes, start, end, reason)`.
pub(crate) fn read_object(py: Python<'_>, failure: ReadFailure) -> PyResult<PyObject> {
    match failure {
        ReadFailure::Io {
            errno,
            winerror,
            message,
        } => tuple_object(
            py,
            vec![
                object(py, "read")?,
                object(py, "os")?,
                object(py, errno)?,
                object(py, message)?,
                object(py, winerror)?,
            ],
        ),
        ReadFailure::Decode {
            bytes,
            start,
            end,
            reason,
        } => tuple_object(
            py,
            vec![
                object(py, "read")?,
                object(py, "decode")?,
                PyBytes::new(py, &bytes).unbind().into_any(),
                object(py, start)?,
                object(py, end)?,
                object(py, reason)?,
            ],
        ),
    }
}

/// A collection's failure payload; an unlistable directory is `("unlistable", path, read)`.
pub(crate) fn stage_failure_object(
    py: Python<'_>,
    tree: &ProjectTree,
    failure: StageFailure,
) -> PyResult<PyObject> {
    match failure {
        StageFailure::Unlistable {
            relative_path,
            error,
        } => tuple_object(
            py,
            vec![
                object(py, "unlistable")?,
                path_object(py, tree, relative_path)?,
                read_object(py, error)?,
            ],
        ),
        StageFailure::Internal(reason) => Err(PyRuntimeError::new_err(reason)),
    }
}

fn outcome_object<T>(
    py: Python<'_>,
    outcome: FileOutcome<T>,
    parsed: impl FnOnce(Python<'_>, T) -> PyResult<PyObject>,
) -> PyResult<PyObject> {
    match outcome {
        FileOutcome::Parsed(value) => parsed(py, value),
        FileOutcome::Unreadable(failure) => read_object(py, failure),
        FileOutcome::Failed(failure) => failure_object(py, failure),
    }
}

/// Each discovered file as `(relative_path, payload)`, or the collection's failure payload.
fn files_object<T>(
    py: Python<'_>,
    tree: &ProjectTree,
    discovered: Result<Vec<DiscoveredFile<T>>, StageFailure>,
    parsed: impl Fn(Python<'_>, T) -> PyResult<PyObject>,
) -> PyResult<PyObject> {
    match discovered {
        Ok(files) => files
            .into_iter()
            .map(|file| {
                Ok((
                    path_object(py, tree, file.relative_path)?,
                    outcome_object(py, file.outcome, &parsed)?,
                ))
            })
            .collect::<PyResult<Vec<(PyObject, PyObject)>>>()?
            .into_py_any(py),
        Err(failure) => stage_failure_object(py, tree, failure),
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

/// A relative path as Python names it: the real, surrogate-escaped name where it is not UTF-8.
pub(crate) fn path_object(
    py: Python<'_>,
    tree: &ProjectTree,
    relative_path: String,
) -> PyResult<PyObject> {
    match tree.raw_relative(&relative_path) {
        Some(raw) => object(py, raw.into_os_string()),
        None => object(py, relative_path),
    }
}

fn entry_rows(py: Python<'_>, entries: &[TreeEntry]) -> PyResult<Vec<(PyObject, bool, bool)>> {
    entries
        .iter()
        .map(|entry| {
            let name: PyObject = match &entry.raw_name {
                Some(raw) => object(py, raw)?,
                None => object(py, &entry.name)?,
            };
            Ok((name, entry.is_dir, entry.is_walkable_dir))
        })
        .collect()
}

fn fact_row(py: Python<'_>, tree: &ProjectTree, fact: DeclarationFileFact) -> PyResult<PyObject> {
    let owning_path: Option<PyObject> = fact
        .owning_path
        .map(|path| path_object(py, tree, path))
        .transpose()?;
    tuple_object(
        py,
        vec![
            path_object(py, tree, fact.relative_path)?,
            object(py, fact.kind.as_str())?,
            object(py, fact.scope_kind.as_str())?,
            path_object(py, tree, fact.ownership_root)?,
            object(py, owning_path)?,
            path_object(py, tree, fact.declaration_root)?,
        ],
    )
}

fn group_row(py: Python<'_>, tree: &ProjectTree, group: DeclarationGroup) -> PyResult<PyObject> {
    tuple_object(
        py,
        vec![
            path_object(py, tree, group.root)?,
            path_object(py, tree, group.directory)?,
        ],
    )
}

/// `("ok", rows)` for a valid layout, or the failure Python raises for it.
fn layout_rows<T>(
    py: Python<'_>,
    tree: &ProjectTree,
    outcome: Result<Vec<T>, DiscoveryFailure>,
    row: fn(Python<'_>, &ProjectTree, T) -> PyResult<PyObject>,
) -> PyResult<PyObject> {
    match outcome {
        Ok(items) => {
            let rows: Vec<PyObject> = items
                .into_iter()
                .map(|item| row(py, tree, item))
                .collect::<PyResult<_>>()?;
            tuple_object(py, vec![object(py, "ok")?, object(py, rows)?])
        }
        Err(failure) => failure_object(py, failure),
    }
}

fn declaration_kind(kind: Option<&str>) -> PyResult<Option<DeclarationKind>> {
    match kind {
        None => Ok(None),
        Some("macro") => Ok(Some(DeclarationKind::Macro)),
        Some("enum") => Ok(Some(DeclarationKind::Enum)),
        Some("constant") => Ok(Some(DeclarationKind::Constant)),
        Some(other) => Err(PyValueError::new_err(format!(
            "unknown declaration kind {other:?}"
        ))),
    }
}

fn yaml_failure_kind(kind: &str) -> PyResult<FailureKind> {
    match kind {
        "source" => Ok(FailureKind::Source),
        "schema" => Ok(FailureKind::Schema),
        other => Err(PyValueError::new_err(format!(
            "unknown YAML file kind {other:?}"
        ))),
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
    fn listings(&self, py: Python<'_>) -> PyResult<Vec<Listing>> {
        let Ok(mut exported) = self.exported.lock() else {
            return Ok(Vec::new());
        };
        read_listings(&self.inner)
            .into_iter()
            .filter(|(directory, _)| exported.insert(directory.clone()))
            .map(|(directory, entries)| {
                Ok((
                    path_object(py, &self.inner, directory)?,
                    entry_rows(py, &entries)?,
                ))
            })
            .collect()
    }
}

/// Discover the model files: one payload per file, or the collection's failure payload.
#[pyfunction]
fn discover_model_files(
    py: Python<'_>,
    request: ModelDiscoveryRequest,
    tree: &NativeProjectTree,
) -> PyResult<PyObject> {
    let python: PythonText = python_semantics(request.python_version, &request.unicode_version)?;
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
    let discovered = py
        .compiler_detach(|| Ok(discover_models(&root, &tree.inner, &options)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    files_object(py, &tree.inner, discovered, model_object)
}

/// Parse in-memory SQL model contents into the payload model discovery returns for a file.
#[pyfunction]
fn parse_model_contents(
    py: Python<'_>,
    request: ModelTextRequest,
    contents: String,
) -> PyResult<PyObject> {
    let options = ModelFileOptions {
        supported_keys: request.supported_keys,
        removed_keys: request.removed_keys,
        extract_implicit_alias_columns: request.extract_implicit_alias_columns,
        extract_output_column_locations: request.extract_output_column_locations,
        python: python_semantics(request.python_version, &request.unicode_version)?,
    };
    let parsed = py
        .compiler_detach(|| Ok(parse_model_text(&request.file_path, contents, &options)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    match parsed {
        Ok(model) => model_object(py, model),
        Err(failure) => failure_object(py, failure),
    }
}

/// The declaration file facts (of one kind, if given) and named groups, or the stage failure.
#[pyfunction]
#[pyo3(signature = (tree, kind=None))]
fn discover_declaration_layout(
    py: Python<'_>,
    tree: &NativeProjectTree,
    kind: Option<&str>,
) -> PyResult<PyObject> {
    let kind: Option<DeclarationKind> = declaration_kind(kind)?;
    let layout: Result<DeclarationLayout, StageFailure> = py
        .compiler_detach(|| Ok(declaration_layout(&tree.inner, kind)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    match layout {
        Ok(layout) => tuple_object(
            py,
            vec![
                layout_rows(py, &tree.inner, layout.file_facts, fact_row)?,
                layout_rows(py, &tree.inner, layout.named_groups, group_row)?,
            ],
        ),
        Err(failure) => stage_failure_object(py, &tree.inner, failure),
    }
}

fn test_block_object(py: Python<'_>, block: SqlTestBlock) -> PyResult<PyObject> {
    tuple_object(
        py,
        vec![
            map_to_python(py, block.header_values)?,
            object(py, block.sql_body)?,
            object(py, block.body_span)?,
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
            object(py, file.body_span)?,
        ],
    )
}

/// The root and options of one SQL test or scenario discovery request.
fn sql_test_inputs(
    request: SqlTestDiscoveryRequest,
) -> PyResult<(ProjectRoot, SqlTestFileOptions)> {
    let python: PythonText = python_semantics(request.python_version, &request.unicode_version)?;
    Ok((
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

/// Discover and split the SQL test files: one payload per file, or the failure payload.
#[pyfunction]
fn discover_sql_test_files(
    py: Python<'_>,
    request: SqlTestDiscoveryRequest,
    tree: &NativeProjectTree,
) -> PyResult<PyObject> {
    let (root, options) = sql_test_inputs(request)?;
    let discovered = py
        .compiler_detach(|| Ok(discover_tests(&root, &tree.inner, &options)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    files_object(py, &tree.inner, discovered, test_file_object)
}

/// Discover and header-parse the scenario files: one payload per file, or the failure payload.
#[pyfunction]
fn discover_scenario_files(
    py: Python<'_>,
    request: SqlTestDiscoveryRequest,
    tree: &NativeProjectTree,
) -> PyResult<PyObject> {
    let (root, options) = sql_test_inputs(request)?;
    let discovered = py
        .compiler_detach(|| Ok(discover_scenarios(&root, &tree.inner, &options)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    files_object(py, &tree.inner, discovered, scenario_object)
}

/// The options of one in-memory SQL test or scenario request.
fn text_options(request: &SqlTestTextRequest) -> PyResult<SqlTestFileOptions> {
    Ok(SqlTestFileOptions {
        test_keys: request.test_keys.clone(),
        scenario_keys: request.scenario_keys.clone(),
        python: python_semantics(request.python_version, &request.unicode_version)?,
    })
}

/// Split in-memory SQL test contents into the payload test discovery returns for a file.
#[pyfunction]
fn parse_sql_test_contents(
    py: Python<'_>,
    request: SqlTestTextRequest,
    contents: String,
) -> PyResult<PyObject> {
    let options: SqlTestFileOptions = text_options(&request)?;
    let parsed = py
        .compiler_detach(|| Ok(parse_sql_test_text(&request.file_path, contents, &options)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    match parsed {
        Ok(file) => test_file_object(py, file),
        Err(failure) => failure_object(py, failure),
    }
}

/// Header-parse in-memory SQL scenario contents into the payload scenario discovery returns.
#[pyfunction]
fn parse_scenario_contents(
    py: Python<'_>,
    request: SqlTestTextRequest,
    contents: String,
) -> PyResult<PyObject> {
    let options: SqlTestFileOptions = text_options(&request)?;
    let parsed = py
        .compiler_detach(|| Ok(parse_scenario_text(&request.file_path, contents, &options)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    match parsed {
        Ok(file) => scenario_object(py, file),
        Err(failure) => failure_object(py, failure),
    }
}

/// `("ok", contents, value)`; a value Python cannot build fails like invalid YAML.
fn loaded_yaml_object(
    py: Python<'_>,
    (file_path, kind): (&str, FailureKind),
    (contents, value): (String, sqlbuild_config::models::ConfigValue),
) -> PyResult<PyObject> {
    match config_value_to_python(py, value) {
        Ok(loaded) => tuple_object(py, vec![object(py, "ok")?, object(py, contents)?, loaded]),
        Err(error) => failure_object(
            py,
            DiscoveryFailure::new(
                kind,
                format!("{file_path} contains invalid YAML: {}", error.value(py)),
            ),
        ),
    }
}

/// Read and load YAML files: one payload per path, or the collection's failure payload.
#[pyfunction]
fn load_yaml_files(
    py: Python<'_>,
    request: YamlDiscoveryRequest,
    relative_paths: Vec<String>,
    tree: &NativeProjectTree,
) -> PyResult<PyObject> {
    let kind: FailureKind = yaml_failure_kind(&request.kind)?;
    let root = ProjectRoot {
        directory: PathBuf::from(request.project_dir),
        display_prefix: request.display_prefix,
    };
    let loaded: Result<Vec<YamlFileOutcome>, StageFailure> = py
        .compiler_detach(|| Ok(load_yaml(&root, &tree.inner, &relative_paths, kind)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    let outcomes: Vec<YamlFileOutcome> = match loaded {
        Ok(outcomes) => outcomes,
        Err(failure) => return stage_failure_object(py, &tree.inner, failure),
    };
    outcomes
        .into_iter()
        .zip(&relative_paths)
        .map(|(outcome, relative_path)| match outcome {
            YamlFileOutcome::Loaded { contents, value } => loaded_yaml_object(
                py,
                (&root.display_path(relative_path), kind),
                (contents, value),
            ),
            YamlFileOutcome::Failed(failure) => failure_object(py, failure),
            YamlFileOutcome::Unreadable(failure) => read_object(py, failure),
        })
        .collect::<PyResult<Vec<PyObject>>>()?
        .into_py_any(py)
}

/// Load one in-memory YAML document as a discovered `kind` file named `file_path` loads.
#[pyfunction]
fn load_yaml_document(
    py: Python<'_>,
    file_path: &str,
    text: String,
    kind: &str,
) -> PyResult<PyObject> {
    let kind: FailureKind = yaml_failure_kind(kind)?;
    match load_yaml_text(file_path, &text, kind) {
        Ok(value) => loaded_yaml_object(py, (file_path, kind), (text, value)),
        Err(failure) => failure_object(py, failure),
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
    module.add_function(wrap_pyfunction!(load_yaml_document, module)?)?;
    module.add_function(wrap_pyfunction!(discover_sql_test_files, module)?)?;
    module.add_function(wrap_pyfunction!(discover_scenario_files, module)?)?;
    module.add_function(wrap_pyfunction!(parse_sql_test_contents, module)?)?;
    module.add_function(wrap_pyfunction!(parse_scenario_contents, module)?)?;
    module.add_class::<NativeProjectTree>()?;
    module.add_function(wrap_pyfunction!(discover_model_files, module)?)?;
    module.add_function(wrap_pyfunction!(parse_model_contents, module)?)?;
    module.add_function(wrap_pyfunction!(discover_declaration_layout, module)?)?;
    Ok(())
}
