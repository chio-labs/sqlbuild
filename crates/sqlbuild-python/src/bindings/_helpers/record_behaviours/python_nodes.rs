//! Graph walks over the natively hosted Python-node graph record.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{
    PyDict, PyDictMethods, PyFrozenSet, PySet, PySetMethods, PyTuple, PyTupleMethods,
};
use sqlbuild_core::graph_walk::main::breadth_first_reach::breadth_first_reach;

use crate::bindings::_helpers::graph::node_set::PyNodeSet;

/// `PythonNodeGraph.selected_sql_refs(selected_names=...)`: SQL references of the selected closure.
pub(crate) fn graph_selected_sql_refs(
    graph: &Bound<'_, PyAny>,
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> PyResult<Py<PyAny>> {
    let py = graph.py();
    let keyword: Option<Bound<'_, PyAny>> = match kwargs {
        Some(kwargs) => kwargs.get_item("selected_names")?,
        None => None,
    };
    let selected: Bound<'_, PyAny> = match keyword {
        Some(selected) => selected,
        None => args.get_item(0)?,
    };
    let nodes_by_name: Bound<'_, PyAny> = graph.getattr("nodes_by_name")?;
    let upstream: Bound<'_, PyAny> = graph.getattr("upstream_deps")?;
    let refs: Bound<'_, PySet> = PySet::empty(py)?;
    let starts: Vec<Bound<'_, PyAny>> = selected.try_iter()?.collect::<PyResult<_>>()?;
    let mut visited: PyNodeSet<'_> = PyNodeSet(PySet::new(py, &starts)?);
    breadth_first_reach(starts, None, &mut visited, |name| {
        upstream
            .call_method1("get", (name, PyTuple::empty(py)))?
            .try_iter()?
            .collect::<PyResult<Vec<Bound<'_, PyAny>>>>()
    })?;
    for name in visited.0.iter() {
        let node: Bound<'_, PyAny> = nodes_by_name.call_method1("get", (name,))?;
        if !node.is_none() {
            for reference in node.getattr("sql_deps")?.try_iter()? {
                refs.add(reference?)?;
            }
        }
    }
    Ok(PyFrozenSet::new(py, refs.iter())?.into_any().unbind())
}
