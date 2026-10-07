//! Native discovery results as the plain data the Python discovery facade materialises.

use pyo3::prelude::{Bound, IntoPyObject, Py, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyTuple;
use pyo3::{IntoPyObjectExt, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_core::text::main::python_alnum_unicode_version::python_alnum_unicode_version;
use sqlbuild_discovery::declarations::main::declaration_layout::declaration_layout;
use sqlbuild_discovery::declarations::models::{
    DeclarationFileFact, DeclarationGroup, DeclarationLayout,
};
use sqlbuild_discovery::model_files::main::discover_model_files::discover_model_files as discover_models;
use sqlbuild_discovery::model_files::models::{DiscoveredModelFile, ModelFileOptions};
use sqlbuild_discovery::models::{
    DiscoveredFile, DiscoveryFailure, FileOutcome, LineColumnSpan, ProjectRoot, StageDeferral,
};
use sqlbuild_discovery::tree::main::listings::read_listings;
use sqlbuild_discovery::tree::models::{ProjectTree, TreeEntry};
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use crate::bindings::_helpers::functions::map_to_python;
use crate::bindings::models::{ModelDiscoveryRequest, NativeProjectTree};
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
        FileOutcome::Failed(failure) => tuple_object(
            py,
            vec![
                object(py, "error")?,
                object(py, failure.kind.as_str())?,
                object(py, failure.message)?,
                object(py, failure.help)?,
            ],
        ),
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
    let root = ProjectRoot {
        directory: PathBuf::from(request.project_dir),
        display_prefix: request.display_prefix,
    };
    let options = ModelFileOptions {
        supported_keys: request.supported_keys,
        removed_keys: request.removed_keys,
        extract_implicit_alias_columns: request.extract_implicit_alias_columns,
        extract_output_column_locations: request.extract_output_column_locations,
    };
    let discovered: Result<Vec<DiscoveredFile<DiscoveredModelFile>>, StageDeferral> = py
        .compiler_detach(|| Ok(discover_models(&root, &tree.inner, &options)))
        .map_err(crate::bindings::_helpers::panics::compiler_error)?;
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
        .map_err(crate::bindings::_helpers::panics::compiler_error)?;
    match layout {
        Ok(layout) => Ok(Some((
            valid_rows(layout.file_facts, fact_row),
            valid_rows(layout.named_groups, group_row),
        ))),
        Err(_deferral) => Ok(None),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeProjectTree>()?;
    module.add_function(wrap_pyfunction!(discover_model_files, module)?)?;
    module.add_function(wrap_pyfunction!(discover_declaration_layout, module)?)?;
    module.add(
        "PYTHON_ALNUM_UNICODE_VERSION",
        python_alnum_unicode_version(),
    )?;
    Ok(())
}
