//! Direct model version identities and honest write hashes over the planner scope.

use std::collections::{HashMap, HashSet};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString};
use pyo3::{pyfunction, wrap_pyfunction};

use sqlbuild_analysis::planner_identity::constants::{
    MODEL_RESOURCE, SEED_RESOURCE, SOURCE_RESOURCE, TABLE_FN_RESOURCE, UDF_RESOURCE,
};
use sqlbuild_analysis::planner_identity::main::expected_graph_identity_hashes::expected_graph_identity_hashes;
use sqlbuild_analysis::planner_identity::main::graph_write_identity_hashes::graph_write_identity_hashes;
use sqlbuild_analysis::planner_identity::main::model_local_identity_hash::model_local_identity_hash;
use sqlbuild_analysis::planner_identity::models::{GraphKey, IdentityGraph, IdentityNode};

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::native_host::user_code::UserCodeHost;
use crate::bindings::_helpers::planner_identity::hashing::{graph_key, model_query_hash};
use crate::bindings::_helpers::planner_identity::metadata::{
    function_local_hashes, model_version_identity_metadata_json, seed_identity,
};
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::records::registry;

const DATACLASSES_MODULE: &str = "dataclasses";

fn key_of(kind: &str, name: &str) -> GraphKey {
    GraphKey {
        kind: kind.to_owned(),
        name: name.to_owned(),
    }
}

fn graph_keys(keys: &Bound<'_, PyAny>) -> PyResult<Vec<GraphKey>> {
    keys.try_iter()?.map(|key| graph_key(&key?)).collect()
}

fn string_pairs(mapping: &Bound<'_, PyAny>) -> PyResult<Vec<(String, String)>> {
    mapping
        .call_method0("items")?
        .try_iter()?
        .map(|item| item?.extract::<(String, String)>())
        .collect()
}

/// `{name: identity.version_hash}` of the discovered Python hooks.
fn hook_version_hashes<'py>(hook_functions: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = hook_functions.py();
    let hashes: Bound<'py, PyDict> = PyDict::new(py);
    let identities: Bound<'py, PyAny> =
        host::entry(py, UserCodeHost::BuildHookIdentities)?.call1((hook_functions,))?;
    for item in identities.call_method0("items")?.try_iter()? {
        let (name, identity): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        hashes.set_item(name, identity.getattr("version_hash")?)?;
    }
    Ok(hashes)
}

/// Current direct model identities from code and upstream identities.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_direct_model_version_identities<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_direct_model_version_identities",
        options,
        (
            &["functions", "scope", "dialect"],
            &["seeds", "source_version_hashes", "hook_functions"],
        ),
    )?;
    let functions: Bound<'py, PyAny> = arguments.value("functions")?;
    let scope: Bound<'py, PyAny> = arguments.value("scope")?;
    let dialect: Option<String> = arguments.value("dialect")?.extract()?;
    let function_hashes: Bound<'py, PyDict> =
        function_local_hashes(&functions, dialect.as_deref())?;
    let hooks: Bound<'py, PyAny> = arguments.value("hook_functions")?;
    let hook_hashes: Bound<'py, PyDict> = if hooks.is_none() {
        PyDict::new(py)
    } else {
        hook_version_hashes(&hooks)?
    };
    let mut graph = IdentityGraph::default();
    for function in functions.try_iter()? {
        let function: Bound<'py, PyAny> = function?;
        let name: String = function.getattr("name")?.extract()?;
        let Some(function_hash) = function_hashes.get_item(&name)? else {
            continue;
        };
        graph.nodes.insert(
            graph_key(&function.getattr("key")?)?,
            IdentityNode {
                upstream_keys: graph_keys(&function.getattr("deps")?)?,
                local_hash: Some(function_hash.extract()?),
            },
        );
    }
    let seed_hashes: Bound<'py, PyDict> = PyDict::new(py);
    let seed_metadata: Bound<'py, PyDict> = PyDict::new(py);
    let seeds: Bound<'py, PyAny> = arguments.value("seeds")?;
    if !seeds.is_none() {
        for seed in seeds.try_iter()? {
            let seed: Bound<'py, PyAny> = seed?;
            let (seed_hash, metadata_json): (String, String) = seed_identity(&seed)?;
            let name: Bound<'py, PyAny> = seed.getattr("name")?;
            seed_hashes.set_item(&name, &seed_hash)?;
            seed_metadata.set_item(&name, metadata_json)?;
        }
    }
    for (name, seed_hash) in string_pairs(seed_hashes.as_any())? {
        graph.nodes.insert(
            key_of(SEED_RESOURCE, &name),
            IdentityNode {
                upstream_keys: Vec::new(),
                local_hash: Some(seed_hash),
            },
        );
    }
    let source_hashes: Bound<'py, PyAny> = arguments.value("source_version_hashes")?;
    if source_hashes.is_truthy()? {
        for (name, source_hash) in string_pairs(&source_hashes)? {
            graph.nodes.insert(
                key_of(SOURCE_RESOURCE, &name),
                IdentityNode {
                    upstream_keys: Vec::new(),
                    local_hash: Some(source_hash),
                },
            );
        }
    }
    let model_metadata: Bound<'py, PyDict> = PyDict::new(py);
    let model_local: Bound<'py, PyDict> = PyDict::new(py);
    let models_by_name: Bound<'py, PyAny> = scope.getattr("models_by_name")?;
    for key in scope.getattr("execution_order")?.try_iter()? {
        let key: Bound<'py, PyAny> = key?;
        let order_key: GraphKey = graph_key(&key)?;
        graph.execution_order.push(order_key.clone());
        if order_key.kind != MODEL_RESOURCE {
            continue;
        }
        let model: Bound<'py, PyAny> = models_by_name.call_method1("get", (&order_key.name,))?;
        if model.is_none() {
            continue;
        }
        let name: String = model_reads::model_name(&model)?;
        let metadata_json: String = model_version_identity_metadata_json(
            &model,
            Some(function_hashes.as_any()),
            Some(hook_hashes.as_any()),
        )?;
        let query_fingerprint: String = model_query_hash(
            py,
            &name,
            (
                &model_reads::query_sql(&model)?.extract::<String>()?,
                dialect.as_deref(),
            ),
        )?;
        let local_hash: String = model_local_identity_hash(&query_fingerprint, &metadata_json);
        model_metadata.set_item(&name, metadata_json)?;
        model_local.set_item(&name, &local_hash)?;
        graph.nodes.insert(
            key_of(MODEL_RESOURCE, &name),
            IdentityNode {
                upstream_keys: graph_keys(&model.getattr("deps")?)?,
                local_hash: Some(local_hash),
            },
        );
    }
    let graph_hashes: HashMap<GraphKey, Option<String>> =
        expected_graph_identity_hashes(&graph).into_iter().collect();
    let version_hashes: Bound<'py, PyDict> = function_hashes.copy()?;
    version_hashes.update(seed_hashes.as_mapping())?;
    for name in model_local.keys() {
        let name: String = name.extract()?;
        if let Some(Some(model_hash)) = graph_hashes.get(&key_of(MODEL_RESOURCE, &name)) {
            version_hashes.set_item(&name, model_hash)?;
        }
    }
    call_with(
        &registry::class(py, RecordId::DirectModelVersionIdentities)?,
        &[
            ("function_local_hashes", function_hashes.into_any()),
            ("seed_version_hashes", seed_hashes.into_any()),
            ("seed_metadata_jsons", seed_metadata.into_any()),
            ("model_metadata_jsons", model_metadata.into_any()),
            ("model_local_hashes", model_local.into_any()),
            ("model_version_hashes", version_hashes.into_any()),
        ],
    )
}

/// Planned write hashes replaced by hashes based on upstreams available this run.
#[pyfunction]
#[pyo3(signature = (**options))]
fn with_honest_model_write_hashes<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "with_honest_model_write_hashes",
        options,
        (
            &["scope", "snapshot", "changes", "version_identities"],
            &["available_model_hashes"],
        ),
    )?;
    let scope: Bound<'py, PyAny> = arguments.value("scope")?;
    let snapshot: Bound<'py, PyAny> = arguments.value("snapshot")?;
    let changes: Bound<'py, PyAny> = arguments.value("changes")?;
    let identities: Bound<'py, PyAny> = arguments.value("version_identities")?;
    let selected_python: Bound<'py, PyAny> = scope.getattr("selected_keys")?;
    let selected: HashSet<GraphKey> = graph_keys(&selected_python)?.into_iter().collect();
    let function_hashes: Vec<(String, String)> =
        string_pairs(&identities.getattr("function_local_hashes")?)?;
    let mut graph = IdentityGraph::default();
    let mut base_hashes: Vec<(GraphKey, String)> = Vec::new();
    let mut function_deps: HashMap<GraphKey, Vec<GraphKey>> = HashMap::new();
    for item in scope
        .getattr("upstream_deps")?
        .call_method0("items")?
        .try_iter()?
    {
        let (key, deps): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        let key: GraphKey = graph_key(&key)?;
        if key.kind == UDF_RESOURCE || key.kind == TABLE_FN_RESOURCE {
            function_deps.insert(key, graph_keys(&deps)?);
        }
    }
    for (name, function_hash) in &function_hashes {
        for kind in [UDF_RESOURCE, TABLE_FN_RESOURCE] {
            let function_key: GraphKey = key_of(kind, name);
            graph.nodes.insert(
                function_key.clone(),
                IdentityNode {
                    upstream_keys: function_deps
                        .get(&function_key)
                        .cloned()
                        .unwrap_or_default(),
                    local_hash: Some(function_hash.clone()),
                },
            );
            base_hashes.push((function_key, function_hash.clone()));
        }
    }
    let recorded_seeds: Bound<'py, PyAny> = snapshot.getattr("fingerprints")?.getattr("seeds")?;
    for (name, seed_hash) in string_pairs(&identities.getattr("seed_version_hashes")?)? {
        let seed_key: GraphKey = key_of(SEED_RESOURCE, &name);
        graph.nodes.insert(
            seed_key.clone(),
            IdentityNode {
                upstream_keys: Vec::new(),
                local_hash: Some(seed_hash.clone()),
            },
        );
        let fingerprint: Bound<'py, PyAny> = recorded_seeds.call_method1("get", (&name,))?;
        let write_hash: String = if selected.contains(&seed_key) || fingerprint.is_none() {
            seed_hash
        } else {
            fingerprint.getattr("version_hash")?.extract()?
        };
        base_hashes.push((seed_key, write_hash));
    }
    let local_hashes: Bound<'py, PyAny> = identities.getattr("model_local_hashes")?;
    for model in scope
        .getattr("models_by_name")?
        .call_method0("values")?
        .try_iter()?
    {
        let model: Bound<'py, PyAny> = model?;
        let name: Bound<'py, PyAny> = model_reads::name_object(&model)?;
        graph.nodes.insert(
            key_of(MODEL_RESOURCE, &name.extract::<String>()?),
            IdentityNode {
                upstream_keys: graph_keys(&model.getattr("deps")?)?,
                local_hash: local_hashes.call_method1("get", (&name,))?.extract()?,
            },
        );
    }
    let recorded_models: Bound<'py, PyAny> = snapshot.getattr("fingerprints")?.getattr("models")?;
    for item in recorded_models.call_method0("items")?.try_iter()? {
        let (name, fingerprint): (String, Bound<'py, PyAny>) = item?.extract()?;
        let version_hash: Bound<'py, PyAny> = fingerprint.getattr("version_hash")?;
        if version_hash.is_truthy()? {
            base_hashes.push((key_of(MODEL_RESOURCE, &name), version_hash.extract()?));
        }
    }
    let available: Bound<'py, PyAny> = arguments.value("available_model_hashes")?;
    if available.is_truthy()? {
        for (name, model_hash) in string_pairs(&available)? {
            base_hashes.push((key_of(MODEL_RESOURCE, &name), model_hash));
        }
    }
    graph.execution_order = graph_keys(&scope.getattr("execution_order")?)?;
    let write_hashes: HashMap<GraphKey, String> =
        graph_write_identity_hashes(&graph, &selected, base_hashes)
            .into_iter()
            .collect();
    let replace: Bound<'py, PyAny> = imported(py, DATACLASSES_MODULE, "replace")?;
    let model_changes: Bound<'py, PyDict> = PyDict::new(py);
    model_changes.update(
        changes
            .getattr("models")?
            .downcast::<PyDict>()?
            .as_mapping(),
    )?;
    let models_by_name: Bound<'py, PyAny> = scope.getattr("models_by_name")?;
    for key in scope.getattr("execution_order")?.try_iter()? {
        let key: Bound<'py, PyAny> = key?;
        let order_key: GraphKey = graph_key(&key)?;
        if order_key.kind != MODEL_RESOURCE || !selected.contains(&order_key) {
            continue;
        }
        let model: Bound<'py, PyAny> = models_by_name.call_method1("get", (&order_key.name,))?;
        if model.is_none() {
            continue;
        }
        let name: Bound<'py, PyAny> = model_reads::name_object(&model)?;
        if local_hashes.call_method1("get", (&name,))?.is_none() {
            continue;
        }
        let Some(write_hash) =
            write_hashes.get(&key_of(MODEL_RESOURCE, &name.extract::<String>()?))
        else {
            continue;
        };
        let Some(change) = model_changes.get_item(&name)? else {
            continue;
        };
        model_changes.set_item(
            &name,
            replace_with(
                &replace,
                &change,
                (
                    "fingerprint_version_hash",
                    PyString::new(py, write_hash).into_any(),
                ),
            )?,
        )?;
    }
    replace_with(&replace, &changes, ("models", model_changes.into_any()))
}

/// Resolved actions with recomputed model changes patched in where available.
#[pyfunction]
#[pyo3(signature = (*, resolved_actions, changes))]
fn merge_recomputed_model_changes<'py>(
    resolved_actions: &Bound<'py, PyAny>,
    changes: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = resolved_actions.py();
    let replace: Bound<'py, PyAny> = imported(py, DATACLASSES_MODULE, "replace")?;
    let recomputed: Bound<'py, PyAny> = changes.getattr("models")?;
    let merged: Bound<'py, PyDict> = PyDict::new(py);
    for item in resolved_actions
        .getattr("models")?
        .call_method0("items")?
        .try_iter()?
    {
        let (name, resolved): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        let mut change: Bound<'py, PyAny> = recomputed.call_method1("get", (&name,))?;
        if change.is_none() {
            change = resolved.getattr("change")?;
        }
        merged.set_item(name, replace_with(&replace, &resolved, ("change", change))?)?;
    }
    replace_with(&replace, resolved_actions, ("models", merged.into_any()))
}

fn replace_with<'py>(
    replace: &Bound<'py, PyAny>,
    instance: &Bound<'py, PyAny>,
    (field, value): (&str, Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let keywords: Bound<'py, PyDict> = PyDict::new(replace.py());
    keywords.set_item(field, value)?;
    replace.call((instance,), Some(&keywords))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(
        build_direct_model_version_identities,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(with_honest_model_write_hashes, module)?)?;
    module.add_function(wrap_pyfunction!(merge_recomputed_model_changes, module)?)
}
