//! Lifecycle regions of a run's selected Python nodes, classified natively.

use std::collections::{BTreeSet, HashMap};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyFrozenSet};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::python_plan::main::run_lifecycle::run_lifecycle;
use sqlbuild_analysis::python_plan::models::{LifecycleNode, RunLifecycle};

const PYTHON_NODE_MODELS_MODULE: &str = "sqlbuild.compiler.python_nodes.models";
const EXTERNAL_CONNECTION_MODE: &str = "external";

/// `build_python_sql_run_lifecycle(*, selection, python_graph)`: a `PythonSqlRunLifecyclePlan`.
#[pyfunction]
#[pyo3(signature = (*, selection, python_graph))]
fn build_python_sql_run_lifecycle<'py>(
    selection: &Bound<'py, PyAny>,
    python_graph: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = selection.py();
    let selected: BTreeSet<String> = selection
        .getattr("python_node_names")?
        .try_iter()?
        .map(|name| name?.extract())
        .collect::<PyResult<_>>()?;
    let mut nodes: HashMap<String, LifecycleNode> = HashMap::new();
    for item in python_graph
        .getattr("nodes_by_name")?
        .call_method0("items")?
        .try_iter()?
    {
        let (name, node): (String, Bound<'py, PyAny>) = item?.extract()?;
        nodes.insert(name, lifecycle_node(&node)?);
    }
    let mut upstream: HashMap<String, Vec<String>> = HashMap::new();
    for item in python_graph
        .getattr("upstream_deps")?
        .call_method0("items")?
        .try_iter()?
    {
        let (name, deps): (String, Bound<'py, PyAny>) = item?.extract()?;
        let deps: Vec<String> = deps
            .try_iter()?
            .map(|dep| dep?.extract())
            .collect::<PyResult<_>>()?;
        upstream.insert(name, deps);
    }
    let lifecycle: RunLifecycle = py.detach(|| run_lifecycle(&selected, &nodes, &upstream));
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item(
        "ingress_python_node_names",
        PyFrozenSet::new(py, lifecycle.ingress_names)?,
    )?;
    arguments.set_item(
        "ingress_loader_names",
        PyFrozenSet::new(py, lifecycle.ingress_loader_names)?,
    )?;
    arguments.set_item(
        "read_side_python_node_names",
        PyFrozenSet::new(py, lifecycle.read_side_names)?,
    )?;
    py.import(PYTHON_NODE_MODELS_MODULE)?
        .getattr("PythonSqlRunLifecyclePlan")?
        .call((), Some(&arguments))
}

fn lifecycle_node(node: &Bound<'_, PyAny>) -> PyResult<LifecycleNode> {
    let loader: Bound<'_, PyAny> = node.getattr("loader")?;
    let external_loader: bool = !loader.is_none()
        && loader.getattr("connection_mode")?.extract::<String>()? == EXTERNAL_CONNECTION_MODE;
    Ok(LifecycleNode {
        kind: node.getattr("kind")?.extract()?,
        external_loader,
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_python_sql_run_lifecycle, module)?)
}
