//! Planner execution edges, their injected origins, stable execution order and buildability over compiled keys.

use std::collections::{HashMap, HashSet};

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{
    PyDict, PyDictMethods, PyFrozenSet, PyList, PyListMethods, PySet, PySetMethods, PyString,
    PyTuple,
};
use pyo3::{pyfunction, wrap_pyfunction};

use sqlbuild_analysis::planner_identity::constants::{
    MODEL_RESOURCE, TABLE_FN_RESOURCE, UDF_RESOURCE,
};
use sqlbuild_analysis::planner_identity::main::missing_upstream_message::missing_upstream_message as message_of;
use sqlbuild_analysis::planner_identity::main::missing_upstreams::missing_upstreams;
use sqlbuild_analysis::planner_identity::main::topological_order::topological_order;
use sqlbuild_analysis::planner_identity::models::{AvailableUpstreams, GraphKey, MissingUpstream};

use crate::bindings::_helpers::boundary::python_calls::KeywordArguments;
use crate::bindings::_helpers::graph::algorithms::{closure, inverted};
use crate::bindings::_helpers::graph::keys::KeyCache;
use crate::bindings::_helpers::planner_identity::hashing::graph_key;
use crate::bindings::_helpers::records::construct::error_class;
use crate::bindings::_helpers::records::construct::new_record_with;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_get_or;
use crate::bindings::_helpers::records::fields::mapping_items;
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use crate::bindings::_helpers::references::explicit_references::{
    GateRow, HookRow, native_execution_gate_edges,
};

const TABLE_FN_TEST_MODE: &str = "table_fn";
const INLINE_SQL_HOOK: &str = "inline SQL";

/// Python keys by graph key, keeping the first object seen for each.
struct KeyObjects<'py> {
    objects: HashMap<GraphKey, Bound<'py, PyAny>>,
}

impl<'py> KeyObjects<'py> {
    fn new() -> Self {
        Self {
            objects: HashMap::new(),
        }
    }

    fn key(&mut self, object: Bound<'py, PyAny>) -> PyResult<GraphKey> {
        let key: GraphKey = graph_key(&object)?;
        self.objects.entry(key.clone()).or_insert(object);
        Ok(key)
    }

    fn keys(&mut self, objects: &Bound<'py, PyAny>) -> PyResult<Vec<GraphKey>> {
        objects
            .try_iter()?
            .map(|object| self.key(object?))
            .collect()
    }

    fn object(&self, key: &GraphKey) -> Bound<'py, PyAny> {
        self.objects[key].clone()
    }

    fn tuple(&self, keys: &[GraphKey], py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(py, keys.iter().map(|key| self.object(key)))
    }
}

fn function_resource(key: &Bound<'_, PyAny>) -> PyResult<bool> {
    let kind: String = native_field(key, "resource_type")?.str()?.extract()?;
    Ok(kind == UDF_RESOURCE || kind == TABLE_FN_RESOURCE)
}

fn hook_label(hook_name: &str, kind: &str) -> String {
    if kind == INLINE_SQL_HOOK {
        return format!("inline SQL hook {hook_name}");
    }
    format!("{kind} hook '{hook_name}'")
}

/// Execution-order edges from lineage and woven SQL test nodes.
#[pyfunction]
pub(crate) fn build_execution_upstream_deps<'py>(
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = project.py();
    let upstream: Bound<'py, PyDict> = PyDict::new(py);
    for collection in ["models", "sources", "seeds", "functions"] {
        for resource in native_field(project, collection)?.try_iter()? {
            let resource: Bound<'py, PyAny> = resource?;
            upstream.set_item(
                native_field(&resource, "key")?,
                PyList::new(
                    py,
                    native_field(&resource, "deps")?
                        .try_iter()?
                        .collect::<PyResult<Vec<_>>>()?,
                )?,
            )?;
        }
    }
    for test in native_field(project, "sql_tests")?.try_iter()? {
        let test: Bound<'py, PyAny> = test?;
        let test_key: Bound<'py, PyAny> = native_field(&test, "key")?;
        let scope_deps: Bound<'py, PyAny> = native_field(&test, "scope_deps")?;
        let deps: Bound<'py, PyList> = PyList::empty(py);
        if native_field(&test, "mode")?.str()?.extract::<String>()? == TABLE_FN_TEST_MODE {
            for scope_dep in scope_deps.try_iter()? {
                let scope_dep: Bound<'py, PyAny> = scope_dep?;
                if function_resource(&scope_dep)? {
                    deps.append(scope_dep)?;
                }
            }
            upstream.set_item(test_key, deps)?;
            continue;
        }
        let seen: Bound<'py, PySet> = PySet::empty(py)?;
        for target_key in scope_deps.try_iter()? {
            let Some(target_deps) = upstream.get_item(target_key?)? else {
                continue;
            };
            for dep_key in target_deps.try_iter()? {
                let dep_key: Bound<'py, PyAny> = dep_key?;
                if !function_resource(&dep_key)? || seen.contains(&dep_key)? {
                    continue;
                }
                seen.add(&dep_key)?;
                deps.append(dep_key)?;
            }
        }
        upstream.set_item(&test_key, deps)?;
        for target_key in scope_deps.try_iter()? {
            if let Some(target_deps) = upstream.get_item(target_key?)? {
                target_deps.downcast::<PyList>()?.append(&test_key)?;
            }
        }
    }
    let (gates, hooks): (Vec<GateRow>, Vec<HookRow>) = native_execution_gate_edges(project)?;
    let cache: KeyCache<'py> = KeyCache::new(py)?;
    let mut extra: Vec<(Bound<'py, PyAny>, Bound<'py, PyAny>)> = Vec::new();
    for gate in &gates {
        extra.push((cache.key(&gate.gated)?, cache.key(&gate.read)?));
    }
    for hook in &hooks {
        extra.push((cache.key(&hook.gated)?, cache.key(&hook.read)?));
    }
    for (gated, read) in extra {
        let gated_upstream: Bound<'py, PyAny> =
            upstream.call_method1("setdefault", (gated, PyList::empty(py)))?;
        if !gated_upstream.contains(&read)? {
            gated_upstream.downcast::<PyList>()?.append(read)?;
        }
    }
    let result: Bound<'py, PyDict> = PyDict::new(py);
    for (key, deps) in upstream.iter() {
        result.set_item(
            key,
            PyTuple::new(py, deps.try_iter()?.collect::<PyResult<Vec<_>>>()?)?,
        )?;
    }
    Ok(result)
}

/// Human-readable origins for execution edges injected beyond pure lineage.
#[pyfunction]
pub(crate) fn build_execution_edge_origins<'py>(
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = project.py();
    let origins: Bound<'py, PyDict> = PyDict::new(py);
    for test in native_field(project, "sql_tests")?.try_iter()? {
        let test: Bound<'py, PyAny> = test?;
        let test_name: String = native_field(&test, "name")?.extract()?;
        for target_key in native_field(&test, "scope_deps")?.try_iter()? {
            let target_key: Bound<'py, PyAny> = target_key?;
            let target_name: String = native_field(&target_key, "name")?.extract()?;
            origins.set_item(
                (target_key, native_field(&test, "key")?),
                format!("SQL test '{test_name}' runs before '{target_name}'"),
            )?;
        }
    }
    let (gates, hooks): (Vec<GateRow>, Vec<HookRow>) = native_execution_gate_edges(project)?;
    let cache: KeyCache<'py> = KeyCache::new(py)?;
    let lineage: Bound<'py, PyAny> = native_field(project, "lineage_graph")?;
    let is_lineage = |gated: &(String, String), read: &(String, String)| -> PyResult<bool> {
        lineage
            .call_method1("upstream", (gated.clone(),))?
            .contains(read.clone())
    };
    for GateRow {
        audit_name,
        target,
        gated,
        read,
    } in &gates
    {
        if is_lineage(gated, read)? {
            continue;
        }
        let _ = origins.call_method1(
            "setdefault",
            (
                (cache.key(gated)?, cache.key(read)?),
                format!("audit '{audit_name}' on '{}' reads '{}'", target.1, read.1),
            ),
        )?;
    }
    for HookRow {
        hook_name,
        gated,
        read,
        hook_type: kind,
        ..
    } in &hooks
    {
        if is_lineage(gated, read)? {
            continue;
        }
        let _ = origins.call_method1(
            "setdefault",
            (
                (cache.key(gated)?, cache.key(read)?),
                format!(
                    "{} on '{}' reads '{}'",
                    hook_label(hook_name, kind),
                    gated.1,
                    read.1
                ),
            ),
        )?;
    }
    Ok(origins)
}

/// Downstream edges keyed by upstream key, each list sorted by `(resource_type, name)`.
#[pyfunction]
pub(crate) fn build_downstream_deps<'py>(
    upstream: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = upstream.py();
    let result: Bound<'py, PyDict> = PyDict::new(py);
    for (key, sources) in inverted(upstream)?.iter() {
        let mut keyed: Vec<(GraphKey, Bound<'py, PyAny>)> = sources
            .try_iter()?
            .map(|source| {
                let source: Bound<'py, PyAny> = source?;
                Ok((graph_key(&source)?, source))
            })
            .collect::<PyResult<_>>()?;
        keyed.sort_by(|left, right| left.0.cmp(&right.0));
        result.set_item(
            key,
            PyTuple::new(py, keyed.into_iter().map(|(_, source)| source))?,
        )?;
    }
    Ok(result)
}

fn planner_input_error(py: Python<'_>, message: String) -> PyErr {
    match error_class(py, ErrorId::PlannerInput).and_then(|class| class.call1((message,))) {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

fn edge_origins<'py>(
    origins: &Bound<'py, PyAny>,
    objects: &mut KeyObjects<'py>,
) -> PyResult<HashMap<(GraphKey, GraphKey), String>> {
    let mut edges: HashMap<(GraphKey, GraphKey), String> = HashMap::new();
    if origins.is_none() {
        return Ok(edges);
    }
    for item in mapping_items(origins)?.try_iter()? {
        let ((dependent, dependency), origin): ((Bound<'py, PyAny>, Bound<'py, PyAny>), String) =
            item?.extract()?;
        edges.insert((objects.key(dependent)?, objects.key(dependency)?), origin);
    }
    Ok(edges)
}

/// All keys in stable dependency order using Kahn's algorithm.
#[pyfunction]
#[pyo3(signature = (*, upstream, injected_edge_origins = None))]
pub(crate) fn topologically_order_keys<'py>(
    upstream: &Bound<'py, PyAny>,
    injected_edge_origins: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = upstream.py();
    let mut objects = KeyObjects::new();
    let mut edges: Vec<(GraphKey, Vec<GraphKey>)> = Vec::new();
    for item in mapping_items(upstream)?.try_iter()? {
        let (key, deps): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        edges.push((objects.key(key)?, objects.keys(&deps)?));
    }
    let origins: HashMap<(GraphKey, GraphKey), String> = match injected_edge_origins {
        Some(origins) => edge_origins(&origins, &mut objects)?,
        None => HashMap::new(),
    };
    let ordered: Vec<GraphKey> =
        topological_order(&edges, &origins).map_err(|message| planner_input_error(py, message))?;
    objects.tuple(&ordered, py)
}

/// Model names reachable downstream from the given keys, including model roots.
#[pyfunction]
#[pyo3(signature = (*, start_keys, downstream_deps))]
pub(crate) fn build_downstream_model_name_closure<'py>(
    start_keys: &Bound<'py, PyAny>,
    downstream_deps: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let py: Python<'py> = downstream_deps.py();
    let starts: Vec<Bound<'py, PyAny>> = start_keys.try_iter()?.collect::<PyResult<_>>()?;
    let mut names: Vec<String> = Vec::new();
    for key in closure(starts, downstream_deps, (true, None))?.iter() {
        let key: GraphKey = graph_key(&key)?;
        if key.kind == MODEL_RESOURCE {
            names.push(key.name);
        }
    }
    PyFrozenSet::new(py, names)
}

fn name_set(names: &Bound<'_, PyAny>) -> PyResult<HashSet<String>> {
    names.try_iter()?.map(|name| name?.extract()).collect()
}

fn missing_rows<'py>(
    missing: &Bound<'py, PyAny>,
    objects: &mut KeyObjects<'py>,
) -> PyResult<Vec<MissingUpstream>> {
    missing
        .try_iter()?
        .map(|entry| {
            let entry: Bound<'py, PyAny> = entry?;
            Ok(MissingUpstream {
                key: objects.key(native_field(&entry, "key")?)?,
                required_by: objects.keys(&native_field(&entry, "required_by")?)?,
            })
        })
        .collect()
}

/// Upstream deps of selected keys that exist neither in scope nor in the warehouse.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn check_buildability<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "check_buildability",
        options,
        (
            &["selected_keys", "upstream_deps", "snapshot"],
            &["deferred_relations", "satisfied_keys"],
        ),
    )?;
    let selected_keys: Bound<'py, PyAny> = arguments.value("selected_keys")?;
    let upstream_deps: Bound<'py, PyAny> = arguments.value("upstream_deps")?;
    let snapshot: Bound<'py, PyAny> = arguments.value("snapshot")?;
    let deferred_relations: Bound<'py, PyAny> = arguments.value("deferred_relations")?;
    let satisfied_keys: Bound<'py, PyAny> = arguments.value("satisfied_keys")?;
    let mut objects = KeyObjects::new();
    let selected: Vec<GraphKey> = objects.keys(&selected_keys)?;
    let mut deps: HashMap<GraphKey, Vec<GraphKey>> = HashMap::new();
    for key in &selected {
        let dep_keys: Bound<'py, PyAny> =
            mapping_get_or(&upstream_deps, objects.object(key), PyTuple::empty(py))?;
        deps.insert(key.clone(), objects.keys(&dep_keys)?);
    }
    let available = AvailableUpstreams {
        satisfied_keys: if satisfied_keys.is_none() {
            HashSet::new()
        } else {
            objects.keys(&satisfied_keys)?.into_iter().collect()
        },
        existing_relations: name_set(&native_field(&snapshot, "existing_relations")?)?,
        deferred_relations: if deferred_relations.is_none() {
            None
        } else {
            Some(name_set(&deferred_relations)?)
        },
    };
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    for missing in missing_upstreams(&selected, &deps, &available) {
        entries.push(new_record_with(
            py,
            RecordId::MissingUpstream,
            &[
                ("key", objects.object(&missing.key)),
                (
                    "required_by",
                    objects.tuple(&missing.required_by, py)?.into_any(),
                ),
            ],
        )?);
    }
    PyTuple::new(py, entries)
}

/// Describe missing upstream keys, naming the audit when only an audit read requires one.
#[pyfunction]
#[pyo3(signature = (*, missing, edge_origins))]
pub(crate) fn missing_upstream_message<'py>(
    missing: &Bound<'py, PyAny>,
    edge_origins: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyString>> {
    let mut objects = KeyObjects::new();
    let rows: Vec<MissingUpstream> = missing_rows(missing, &mut objects)?;
    let origins: HashMap<(GraphKey, GraphKey), String> =
        self::edge_origins(edge_origins, &mut objects)?;
    Ok(PyString::new(missing.py(), &message_of(&rows, &origins)))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_execution_upstream_deps, module)?)?;
    module.add_function(wrap_pyfunction!(build_execution_edge_origins, module)?)?;
    module.add_function(wrap_pyfunction!(build_downstream_deps, module)?)?;
    module.add_function(wrap_pyfunction!(topologically_order_keys, module)?)?;
    module.add_function(wrap_pyfunction!(
        build_downstream_model_name_closure,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(check_buildability, module)?)?;
    module.add_function(wrap_pyfunction!(missing_upstream_message, module)?)
}
