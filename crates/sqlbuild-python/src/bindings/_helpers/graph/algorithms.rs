//! Breadth-first closure, edge inversion and path nodes over any Python-keyed edge mapping.

use std::collections::VecDeque;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{
    PyDict, PyDictMethods, PyFrozenSet, PyList, PyListMethods, PySet, PySetMethods, PyTuple,
};
use pyo3::{pyfunction, wrap_pyfunction};

const BUILTINS_MODULE: &str = "builtins";

/// Keys within `max_depth` edges of any start, plus the starts when `include_starts`.
pub(crate) fn closure<'py>(
    starts: Vec<Bound<'py, PyAny>>,
    edges: &Bound<'py, PyAny>,
    (include_starts, max_depth): (bool, Option<i64>),
) -> PyResult<Bound<'py, PySet>> {
    let py: Python<'py> = edges.py();
    let visited: Bound<'py, PySet> = PySet::empty(py)?;
    if include_starts {
        for start in &starts {
            visited.add(start)?;
        }
    }
    let mut frontier: VecDeque<(Bound<'py, PyAny>, i64)> =
        starts.into_iter().map(|start| (start, 0)).collect();
    let none: Bound<'py, PyTuple> = PyTuple::empty(py);
    while let Some((current, depth)) = frontier.pop_front() {
        if max_depth.is_some_and(|maximum| depth >= maximum) {
            continue;
        }
        for neighbor in edges.call_method1("get", (&current, &none))?.try_iter()? {
            let neighbor: Bound<'py, PyAny> = neighbor?;
            if visited.contains(&neighbor)? {
                continue;
            }
            visited.add(&neighbor)?;
            frontier.push_back((neighbor, depth + 1));
        }
    }
    Ok(visited)
}

/// Keys within `max_depth` edges of any start, plus the starts when requested.
#[pyfunction]
#[pyo3(signature = (*, starts, edges, include_starts, max_depth = None))]
fn transitive_closure_many<'py>(
    starts: &Bound<'py, PyAny>,
    edges: &Bound<'py, PyAny>,
    include_starts: bool,
    max_depth: Option<i64>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let starts: Vec<Bound<'py, PyAny>> = starts.try_iter()?.collect::<PyResult<_>>()?;
    let visited: Bound<'py, PySet> = closure(starts, edges, (include_starts, max_depth))?;
    PyFrozenSet::new(edges.py(), visited.iter())
}

/// All graph keys reachable from a starting key.
#[pyfunction]
#[pyo3(signature = (*, start, edges, max_depth = None))]
fn transitive_closure<'py>(
    start: Bound<'py, PyAny>,
    edges: &Bound<'py, PyAny>,
    max_depth: Option<i64>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let visited: Bound<'py, PySet> = closure(vec![start], edges, (false, max_depth))?;
    PyFrozenSet::new(edges.py(), visited.iter())
}

/// Reversed edges: every source key first, then each new target in first-seen order.
fn inverted<'py>(edges: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = edges.py();
    let inverted: Bound<'py, PyDict> = PyDict::new(py);
    for key in edges.try_iter()? {
        inverted.set_item(key?, PyList::empty(py))?;
    }
    for item in edges.call_method0("items")?.try_iter()? {
        let (source, targets): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        for target in targets.try_iter()? {
            let target: Bound<'py, PyAny> = target?;
            let sources: Bound<'py, PyList> = match inverted.get_item(&target)? {
                Some(sources) => sources.downcast_into()?,
                None => {
                    let sources: Bound<'py, PyList> = PyList::empty(py);
                    inverted.set_item(&target, &sources)?;
                    sources
                }
            };
            sources.append(&source)?;
        }
    }
    Ok(inverted)
}

/// Reversed directed graph edges, each source list sorted by `sort_key` when given.
#[pyfunction]
#[pyo3(signature = (*, edges, sort_key = None))]
fn invert_edges<'py>(
    edges: &Bound<'py, PyAny>,
    sort_key: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = edges.py();
    let inverted: Bound<'py, PyDict> = inverted(edges)?;
    let sorted: Bound<'py, PyAny> = py.import(BUILTINS_MODULE)?.getattr("sorted")?;
    let result: Bound<'py, PyDict> = PyDict::new(py);
    for (key, sources) in inverted.iter() {
        let sources: Bound<'py, PyAny> = match sort_key {
            None => sources,
            Some(sort_key) => {
                let keywords: Bound<'py, PyDict> = PyDict::new(py);
                keywords.set_item("key", sort_key)?;
                sorted.call((sources,), Some(&keywords))?
            }
        };
        result.set_item(
            key,
            PyTuple::new(py, sources.try_iter()?.collect::<PyResult<Vec<_>>>()?)?,
        )?;
    }
    Ok(result)
}

/// Keys on directed paths between two endpoints, or `None` when `end` is not downstream.
#[pyfunction]
#[pyo3(signature = (*, start, end, downstream))]
fn path_nodes<'py>(
    start: Bound<'py, PyAny>,
    end: Bound<'py, PyAny>,
    downstream: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyFrozenSet>>> {
    let py: Python<'py> = downstream.py();
    let reachable: Bound<'py, PySet> = closure(vec![start.clone()], downstream, (false, None))?;
    if !reachable.contains(&end)? {
        return Ok(None);
    }
    let upstream: Bound<'py, PyDict> = inverted(downstream)?;
    let upstream_from_end: Bound<'py, PySet> = PySet::empty(py)?;
    let mut stack: Vec<Bound<'py, PyAny>> = vec![end.clone()];
    while let Some(current) = stack.pop() {
        if upstream_from_end.contains(&current)? {
            continue;
        }
        upstream_from_end.add(&current)?;
        let Some(parents) = upstream.get_item(&current)? else {
            continue;
        };
        for parent in parents.try_iter()? {
            let parent: Bound<'py, PyAny> = parent?;
            if reachable.contains(&parent)? || parent.eq(&start)? {
                stack.push(parent);
            }
        }
    }
    let nodes: Bound<'py, PyAny> = reachable
        .call_method1("__and__", (&upstream_from_end,))?
        .call_method1("__or__", (PySet::new(py, [&start, &end])?,))?;
    Ok(Some(PyFrozenSet::new(
        py,
        nodes.try_iter()?.collect::<PyResult<Vec<_>>>()?,
    )?))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(transitive_closure, module)?)?;
    module.add_function(wrap_pyfunction!(transitive_closure_many, module)?)?;
    module.add_function(wrap_pyfunction!(invert_edges, module)?)?;
    module.add_function(wrap_pyfunction!(path_nodes, module)?)?;
    Ok(())
}
