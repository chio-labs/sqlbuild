//! Model ordering, selection and metadata at the migration discovery boundary.

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::graph::node_set::PyNodeSet;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::native_host::user_code::UserCodeHost;
use crate::bindings::_helpers::planner_migrations::column_objects::native;
use crate::bindings::_helpers::planner_phases::runtime::runtime_field;
use crate::bindings::_helpers::records::ids::NativeAttr;
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PySet, PySetMethods};
use sqlbuild_analysis::planner_migrations::main::discovery_order::discovery_order;
use sqlbuild_core::graph_walk::main::breadth_first_reach::breadth_first_reach;
use std::collections::BTreeMap;

pub(super) fn ordered<'py>(runtime: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut models: BTreeMap<String, Bound<'py, PyAny>> = BTreeMap::new();
    let mut dependencies: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for item in runtime_field(&runtime, |runtime| &runtime.project)?
        .getattr("models")?
        .try_iter()?
    {
        let item = item?;
        let name: String = item.getattr("name")?.extract()?;
        let mut upstream: Vec<String> = Vec::new();
        for dependency in item.getattr("deps")?.try_iter()? {
            let dependency = dependency?;
            if dependency.getattr("resource_type")?.eq("model")? {
                upstream.push(dependency.getattr("name")?.extract()?);
            }
        }
        dependencies.insert(name.clone(), upstream);
        models.insert(name, item);
    }
    Ok(discovery_order(&dependencies)
        .iter()
        .map(|name| models[name].clone())
        .collect())
}

pub(super) fn triggered(
    models: &[Bound<'_, PyAny>],
    scope: &Bound<'_, PyAny>,
    snapshot: &Bound<'_, PyAny>,
    declared: &Bound<'_, PyDict>,
) -> PyResult<bool> {
    let py = scope.py();
    let selected: Vec<Bound<'_, PyAny>> = scope
        .getattr("selected_keys")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let mut relevant = PyNodeSet(PySet::new(py, &selected)?);
    breadth_first_reach(selected, None, &mut relevant, |key| {
        scope
            .getattr("upstream_deps")?
            .call_method1("get", (key, pyo3::types::PyTuple::empty(py)))?
            .try_iter()?
            .collect::<PyResult<Vec<Bound<'_, PyAny>>>>()
    })?;
    let relevant = relevant.0;
    let fingerprints = snapshot.getattr("fingerprints")?.getattr("models")?;
    for item in models {
        let name = item.getattr("name")?;
        if relevant.contains(item.getattr("key")?)?
            && !fingerprints.contains(&name)?
            && !declared.contains(&name)?
        {
            return Ok(true);
        }
    }
    Ok(false)
}

pub(super) fn metadata<'py>(
    runtime: &Bound<'py, PyAny>,
    models: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyDict>> {
    let py = runtime.py();
    let project = runtime_field(&runtime, |runtime| &runtime.project)?;
    let functions = native(
        py,
        NativeAttr::BuildFunctionLocalHashes,
        &[
            ("functions", project.getattr("functions")?),
            ("dialect", project.getattr("sql_analysis_dialect")?),
        ],
    )?;
    let identities = host::entry(py, UserCodeHost::BuildHookIdentities)?
        .call1((project.getattr("hook_functions")?,))?;
    let hooks = PyDict::new(py);
    for pair in identities.call_method0("items")?.try_iter()? {
        let pair = pair?;
        hooks.set_item(
            pair.get_item(0)?,
            pair.get_item(1)?.getattr("version_hash")?,
        )?;
    }
    let result = PyDict::new(py);
    for item in models {
        result.set_item(
            item.getattr("name")?,
            call_with(
                &registry::native(py, NativeAttr::BuildModelVersionIdentityMetadataJson)?,
                &[
                    ("model", item.clone()),
                    ("function_local_hashes", functions.clone()),
                    ("hook_version_hashes", hooks.clone().into_any()),
                ],
            )?,
        )?;
    }
    Ok(result)
}
