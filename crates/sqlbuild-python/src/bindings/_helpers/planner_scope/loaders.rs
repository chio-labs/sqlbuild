//! Loader dependency mapping and synthetic source boundary construction.

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::graph::keys::KeyCache;
use crate::bindings::_helpers::graph::views::edge_dict;
use crate::bindings::_helpers::planner_scope::values::{
    dependency_names, edges, keys, loader_graph, loader_names, project_graph,
};
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, IntoPyObject, PyAny, PyAnyMethods, PyResult, pyfunction};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyTuple};
use sqlbuild_analysis::planner_scope::main::{
    expand_loaders::expand_loaders, intermediate_sources::intermediate_sources,
};
use std::collections::HashSet;

#[pyfunction]
#[pyo3(signature = (*, loader_function, loader_functions))]
pub(crate) fn upstream_loader_dependency_names<'py>(
    loader_function: &Bound<'py, PyAny>,
    loader_functions: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let graph = loader_graph(loader_functions)?;
    let names = loader_names(loader_functions)?;
    let deps = dependency_names(loader_function, &names)?;
    PyTuple::new(loader_function.py(), graph.upstream(&deps))
}

#[pyfunction]
#[pyo3(signature = (*, project, loader))]
pub(crate) fn loader_to_source_entry<'py>(
    project: &Bound<'py, PyAny>,
    loader: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    let name = loader.getattr("name")?;
    let mut destination = loader.getattr("destination")?;
    if destination.is_none() {
        destination = format!("__loader__{}", name.extract::<String>()?)
            .into_pyobject(py)?
            .into_any();
    }
    let parts = call_with(
        &registry::native(py, NativeAttr::LoaderDestinationPartsFunction)?,
        &[
            ("destination", destination),
            (
                "default_database",
                project.getattr("effective_target_database")?,
            ),
            (
                "default_schema",
                project.getattr("effective_target_schema")?,
            ),
        ],
    )?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("name", &name)?;
    kwargs.set_item("loader", &name)?;
    for field in ["database", "schema", "table"] {
        kwargs.set_item(field, parts.getattr(field)?)?;
    }
    for field in [
        "write_strategy",
        "cursor_column",
        "unique_key",
        "contract",
        "columns",
    ] {
        kwargs.set_item(field, loader.getattr(field)?)?;
    }
    let meta = PyDict::new(py);
    meta.set_item("sqlbuild_loader_node", true)?;
    kwargs.set_item("meta", meta)?;
    registry::class(py, RecordId::SourceEntry)?.call((), Some(&kwargs))
}

pub(crate) fn intermediate_map<'py>(
    project: &Bound<'py, PyAny>,
    selected: &Bound<'py, PyAny>,
    upstream: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let graph = project_graph(project)?;
    let names = intermediate_sources(&graph, &keys(selected)?, upstream);
    let loaders = PyDict::new(project.py());
    for loader in project.getattr("loader_functions")?.try_iter()? {
        let loader = loader?;
        loaders.set_item(loader.getattr("name")?, &loader)?;
    }
    let result = PyDict::new(project.py());
    for name in names {
        if let Some(loader) = loaders.get_item(&name)? {
            result.set_item(&name, loader_to_source_entry(project, &loader)?)?;
        }
    }
    Ok(result)
}

#[pyfunction]
#[pyo3(signature = (*, project, selected_keys))]
pub(crate) fn build_intermediate_source_map<'py>(
    project: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    intermediate_map(project, selected_keys, false)
}

#[pyfunction]
#[pyo3(signature = (*, project, selected_keys))]
pub(crate) fn build_upstream_intermediate_source_map<'py>(
    project: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    intermediate_map(project, selected_keys, true)
}

#[pyfunction]
#[pyo3(signature = (*, project, selected_keys, upstream_deps, executable_dependency_source_keys = None))]
pub(crate) fn expand_selected_loader_dependencies<'py>(
    project: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
    upstream_deps: &Bound<'py, PyAny>,
    executable_dependency_source_keys: Option<&Bound<'py, PyAny>>,
) -> PyResult<(Bound<'py, PyFrozenSet>, Bound<'py, PyDict>)> {
    let graph = project_graph(project)?;
    let selected = keys(selected_keys)?;
    let upstream = edges(upstream_deps)?;
    let executable = executable_dependency_source_keys
        .map(keys)
        .transpose()?
        .unwrap_or_default()
        .into_iter()
        .collect::<HashSet<_>>();
    let (selected, upstream) = expand_loaders(&graph, selected, upstream, &executable);
    let cache = KeyCache::new(project.py())?;
    Ok((
        PyFrozenSet::new(project.py(), cache.keys(&selected)?)?,
        edge_dict(&cache, &upstream)?,
    ))
}
