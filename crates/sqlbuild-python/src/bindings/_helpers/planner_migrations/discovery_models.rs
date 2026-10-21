//! Model ordering, selection and metadata at the migration discovery boundary.

use sqlbuild_host::entries::models::UserCodeHost;

use crate::bindings::_helpers::compiled_views::model_reads;
use crate::bindings::_helpers::compiled_views::project_reads;
use crate::bindings::_helpers::graph::node_set::PyNodeSet;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::planner_identity::metadata::build_function_local_hashes;
use crate::bindings::_helpers::planner_identity::metadata::build_model_version_identity_metadata_json;
use crate::bindings::_helpers::planner_phases::objects::object;
use crate::bindings::_helpers::planner_phases::runtime::runtime_field;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_items;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PySet, PySetMethods};
use sqlbuild_analysis::planner_migrations::main::discovery_order::discovery_order;
use sqlbuild_core::graph_walk::main::breadth_first_reach::breadth_first_reach;
use std::collections::BTreeMap;

pub(super) fn ordered<'py>(runtime: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut models: BTreeMap<String, Bound<'py, PyAny>> = BTreeMap::new();
    let mut dependencies: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for item in
        project_reads::models(&runtime_field(runtime, |runtime| &runtime.project)?)?.try_iter()?
    {
        let item = item?;
        let name: String = model_reads::name_object(&item)?.extract()?;
        let mut upstream: Vec<String> = Vec::new();
        for dependency in model_reads::deps(&item)?.try_iter()? {
            let dependency = dependency?;
            if native_field(&dependency, "resource_type")?.eq("model")? {
                upstream.push(native_field(&dependency, "name")?.extract()?);
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
    let selected: Vec<Bound<'_, PyAny>> = native_field(scope, "selected_keys")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let mut relevant = PyNodeSet(PySet::new(py, &selected)?);
    breadth_first_reach(selected, None, &mut relevant, |key| {
        native_field(scope, "upstream_deps")?
            .call_method1("get", (key, pyo3::types::PyTuple::empty(py)))?
            .try_iter()?
            .collect::<PyResult<Vec<Bound<'_, PyAny>>>>()
    })?;
    let relevant = relevant.0;
    let fingerprints = native_field(&native_field(snapshot, "fingerprints")?, "models")?;
    for item in models {
        let name = model_reads::name_object(item)?;
        if relevant.contains(model_reads::model_key(item)?)?
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
    let project = runtime_field(runtime, |runtime| &runtime.project)?;
    let functions = object(
        py,
        build_function_local_hashes(
            &project_reads::functions(&project)?,
            native_field(&project, "sql_analysis_dialect")?
                .extract::<Option<String>>()?
                .as_deref(),
        )?,
    )?;
    let identities = host::entry(py, UserCodeHost::BuildHookIdentities)?
        .call1((native_field(&project, "hook_functions")?,))?;
    let hooks = PyDict::new(py);
    for pair in mapping_items(&identities)?.try_iter()? {
        let pair = pair?;
        hooks.set_item(
            pair.get_item(0)?,
            native_field(&pair.get_item(1)?, "version_hash")?,
        )?;
    }
    let result = PyDict::new(py);
    for item in models {
        result.set_item(
            model_reads::name_object(item)?,
            object(
                py,
                build_model_version_identity_metadata_json(
                    item,
                    functions.extract::<Option<Bound<PyAny>>>()?,
                    hooks.clone().into_any().extract::<Option<Bound<PyAny>>>()?,
                )?,
            )?,
        )?;
    }
    Ok(result)
}
