//! Graph walks over the natively hosted Python-node graph record.

use std::collections::HashSet;

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{
    PyDict, PyDictMethods, PyFrozenSet, PySet, PySetMethods, PyTuple, PyTupleMethods,
};

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
    let mut pending: Vec<String> = selected
        .try_iter()?
        .map(|name| name?.extract::<String>())
        .collect::<PyResult<_>>()?;
    let mut visited: HashSet<String> = HashSet::new();
    while let Some(name) = pending.pop() {
        if !visited.insert(name.clone()) {
            continue;
        }
        let node: Bound<'_, PyAny> = nodes_by_name.call_method1("get", (name.as_str(),))?;
        if !node.is_none() {
            for reference in node.getattr("sql_deps")?.try_iter()? {
                refs.add(reference?)?;
            }
        }
        let parents: Bound<'_, PyAny> =
            upstream.call_method1("get", (name.as_str(), PyTuple::empty(py)))?;
        for parent in parents.try_iter()? {
            pending.push(parent?.extract()?);
        }
    }
    Ok(PyFrozenSet::new(py, refs.iter())?.into_any().unbind())
}
