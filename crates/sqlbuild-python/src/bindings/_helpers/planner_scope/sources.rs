//! Existing source and load plan models materialised at the Python boundary.

use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::graph::algorithms::closure;
use crate::bindings::_helpers::planner_scope::loaders::intermediate_map;
use crate::bindings::_helpers::planner_scope::values::MODELS;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, pyfunction};
use pyo3::types::{PyBool, PyDict, PyTuple};
use pyo3::types::{PyDictMethods, PySetMethods};
use sqlbuild_analysis::planner_scope::constants::SOURCE;

const EXECUTION_TYPES: &str = "sqlbuild.runtime.contracts.types";

#[pyfunction]
#[pyo3(signature = (*, project, selected_keys, upstream_deps = None))]
pub(crate) fn build_source_load_map<'py>(
    project: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
    upstream_deps: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let relevant = upstream_deps
        .map(|edges| {
            closure(
                selected_keys.try_iter()?.collect::<PyResult<Vec<_>>>()?,
                edges,
                (true, None),
            )
        })
        .transpose()?;
    let result = PyDict::new(project.py());
    for source in project.getattr("sources")?.try_iter()? {
        let source = source?;
        if let Some(keys) = &relevant
            && !keys.contains(source.getattr("key")?)?
        {
            continue;
        }
        let entry = source.getattr("source_entry")?;
        result.set_item(entry.getattr("name")?, entry)?;
    }
    for upstream in [false, true] {
        for (key, entry) in intermediate_map(project, selected_keys, upstream)?.iter() {
            result.set_item(key, entry)?;
        }
    }
    Ok(result)
}

#[pyfunction]
#[pyo3(signature = (*, execution_order, selected_keys, source_map, is_reload))]
pub(crate) fn build_source_load_entries<'py>(
    execution_order: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
    source_map: &Bound<'py, PyDict>,
    is_reload: bool,
) -> PyResult<Bound<'py, PyTuple>> {
    let py = execution_order.py();
    let class = imported(py, MODELS, "SourceLoadPlanEntry")?;
    let kinds = imported(py, EXECUTION_TYPES, "ExecutionResourceKind")?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in execution_order.try_iter()? {
        let key = key?;
        if !selected_keys.contains(&key)?
            || key.getattr("resource_type")?.str()?.extract::<String>()? != SOURCE
        {
            continue;
        }
        let Some(entry) = source_map.get_item(key.getattr("name")?)? else {
            continue;
        };
        if entry.getattr("loader")?.is_none() {
            continue;
        }
        let kwargs = PyDict::new(py);
        kwargs.set_item("key", key)?;
        for field in [
            "name",
            "loader",
            "write_strategy",
            "cursor_column",
            "unique_key",
        ] {
            kwargs.set_item(field, entry.getattr(field)?)?;
        }
        let table = entry.getattr("table")?;
        kwargs.set_item(
            "destination",
            if table.is_truthy()? {
                table
            } else {
                entry.getattr("name")?
            },
        )?;
        let intermediate = entry
            .getattr("meta")?
            .call_method1("get", ("sqlbuild_loader_node",))?
            .is(PyBool::new(py, true));
        kwargs.set_item(
            "resource_kind",
            kinds.getattr(if intermediate { "LOADER" } else { "SOURCE" })?,
        )?;
        kwargs.set_item("is_reload", is_reload)?;
        let integration = entry.getattr("integration_loader")?;
        kwargs.set_item(
            "integration_kind",
            if integration.is_none() {
                py.None().into_bound(py)
            } else {
                integration.getattr("kind")?
            },
        )?;
        entries.push(class.call((), Some(&kwargs))?);
    }
    PyTuple::new(py, entries)
}
