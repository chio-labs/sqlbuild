//! Project-tree queries custom rules run over the discovered paths.

use std::ffi::OsString;
use std::path::PathBuf;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyString, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_rules::project_tree::errors::RelativePartsError;
use sqlbuild_rules::project_tree::main::project_relative_parts::project_relative_parts;
use sqlbuild_rules::project_tree::main::project_tree_children::project_tree_children;
use sqlbuild_rules::project_tree::main::project_tree_descendants::project_tree_descendants;
use sqlbuild_rules::project_tree::main::project_tree_glob::project_tree_glob;
use sqlbuild_rules::project_tree::main::tracked_text_path::tracked_text_path;

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::records::ids::ErrorId;
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::rules::rule_api::{usage_error_for, validate_project_relative};

const PATHLIB_MODULE: &str = "pathlib";

/// `pathlib.Path(value)`, raising exactly as `Path` does for an unsupported value.
fn python_path<'py>(value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    imported(value.py(), PATHLIB_MODULE, "Path")?.call1((value,))
}

/// The nodes and their `value`s as raw paths.
fn node_values<'py>(nodes: &Bound<'py, PyAny>) -> PyResult<(Vec<Bound<'py, PyAny>>, Vec<PathBuf>)> {
    let nodes: Vec<Bound<'py, PyAny>> = nodes.try_iter()?.collect::<PyResult<_>>()?;
    let values: Vec<PathBuf> = nodes
        .iter()
        .map(|node| node.getattr("value")?.extract())
        .collect::<PyResult<_>>()?;
    Ok((nodes, values))
}

/// The nodes at `indexes`, in order.
fn selected<'py>(
    py: Python<'py>,
    nodes: &[Bound<'py, PyAny>],
    indexes: Vec<usize>,
) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(py, indexes.into_iter().map(|index| nodes[index].clone()))
}

/// The nodes directly inside the project directory `path`.
#[pyfunction]
fn project_tree_child_nodes<'py>(
    nodes: &Bound<'py, PyAny>,
    path: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let directory: PathBuf = python_path(path)?.extract()?;
    let (nodes, values) = node_values(nodes)?;
    let values: Vec<&std::path::Path> = values.iter().map(PathBuf::as_path).collect();
    selected(
        path.py(),
        &nodes,
        project_tree_children(&values, &directory),
    )
}

/// The nodes below the project directory `path`, or every node for an empty path.
#[pyfunction]
fn project_tree_descendant_nodes<'py>(
    nodes: &Bound<'py, PyAny>,
    path: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let directory: Option<PathBuf> = if path.is_truthy()? {
        Some(python_path(path)?.extract()?)
    } else {
        None
    };
    let (nodes, values) = node_values(nodes)?;
    let values: Vec<&std::path::Path> = values.iter().map(PathBuf::as_path).collect();
    selected(
        path.py(),
        &nodes,
        project_tree_descendants(&values, directory.as_deref()),
    )
}

/// The nodes a project-relative shell-style pattern matches.
#[pyfunction]
fn project_tree_glob_nodes<'py>(
    nodes: &Bound<'py, PyAny>,
    pattern: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = pattern.py();
    validate_project_relative(pattern)?;
    let pattern: PathBuf = pattern.extract()?;
    let (nodes, values) = node_values(nodes)?;
    let values: Vec<&std::path::Path> = values.iter().map(PathBuf::as_path).collect();
    selected(py, &nodes, project_tree_glob(&values, &pattern))
}

/// The values of the file nodes rules may read as tracked text, in order.
#[pyfunction]
fn tracked_text_file_values<'py>(nodes: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyTuple>> {
    let mut values: Vec<Bound<'py, PyAny>> = Vec::new();
    for node in nodes.try_iter()? {
        let node: Bound<'py, PyAny> = node?;
        if !node.getattr("is_file")?.is_truthy()? {
            continue;
        }
        let value: Bound<'py, PyAny> = node.getattr("value")?;
        if tracked_text_path(&value.extract::<PathBuf>()?) {
            values.push(value);
        }
    }
    PyTuple::new(nodes.py(), values)
}

/// `RuleUsageError(f"project path {path} is not beneath {under}")`, spelled by Python.
fn not_beneath(path: &Bound<'_, PyAny>, under: &Bound<'_, PyAny>) -> PyErr {
    let py: Python<'_> = path.py();
    let message = path.str().and_then(|path_text| {
        let under_text = under.str()?;
        PyString::new(py, "project path ")
            .as_any()
            .add(path_text)?
            .add(" is not beneath ")?
            .add(under_text)
    });
    match message.and_then(|message| {
        registry::error(py, ErrorId::RuleUsage).and_then(|class| class.call1((message,)))
    }) {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// `path`'s parts relative to the resolved project `root`, then to `under` when given.
#[pyfunction]
#[pyo3(signature = (*, root, path, under))]
fn project_tree_relative_parts<'py>(
    root: &Bound<'py, PyAny>,
    path: &Bound<'py, PyAny>,
    under: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = path.py();
    let relative: Bound<'py, PyAny> = python_path(path)?;
    let under_path: Option<PathBuf> = if under.is_truthy()? {
        Some(python_path(under)?.extract()?)
    } else {
        None
    };
    let parts: Vec<OsString> = match project_relative_parts(
        &relative.extract::<PathBuf>()?,
        &root.extract::<PathBuf>()?,
        under_path.as_deref(),
        |_| relative.call_method0("resolve")?.extract::<PathBuf>(),
    ) {
        Ok(parts) => parts,
        Err(RelativePartsError::Resolve(error)) if !error.is_instance_of::<PyValueError>(py) => {
            return Err(error);
        }
        Err(RelativePartsError::Resolve(_) | RelativePartsError::Escapes) => {
            return Err(usage_error_for("project path escapes the project: ", path));
        }
        Err(RelativePartsError::NotBeneath) => return Err(not_beneath(path, under)),
    };
    let parts: Vec<Bound<'py, PyAny>> = parts
        .into_iter()
        .map(|part| Ok(part.into_pyobject(py)?.into_any()))
        .collect::<PyResult<_>>()?;
    PyTuple::new(py, parts)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(project_tree_child_nodes, module)?)?;
    module.add_function(wrap_pyfunction!(project_tree_descendant_nodes, module)?)?;
    module.add_function(wrap_pyfunction!(project_tree_glob_nodes, module)?)?;
    module.add_function(wrap_pyfunction!(tracked_text_file_values, module)?)?;
    module.add_function(wrap_pyfunction!(project_tree_relative_parts, module)?)?;
    Ok(())
}
