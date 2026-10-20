//! Ordering edges attached audits and model hooks add, and the keys hooks and SQL refs name.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::graph::keys::KeyCache;
use crate::bindings::_helpers::records::construct::{enum_from_value, record_class};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_get;
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::references::explicit_references::{
    GateRow, HookRow, native_execution_gate_edges,
};

const PATHLIB_MODULE: &str = "pathlib";
/// The model config keys whose entries are hooks, in lifecycle order.
const MODEL_HOOK_KEYS: [&str; 2] = ["pre_hooks", "post_hooks"];

fn keyword_call<'py>(
    callable: &Bound<'py, PyAny>,
    pairs: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let keywords: Bound<'py, PyDict> = PyDict::new(callable.py());
    for (name, value) in pairs {
        keywords.set_item(name, value)?;
    }
    callable.call((), Some(&keywords))
}

/// Edges from each extra audit read to its model or seed target, or source triggers.
#[pyfunction]
#[pyo3(signature = (*, project))]
fn attached_audit_gate_edges<'py>(
    py: Python<'py>,
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let (gates, _): (Vec<GateRow>, Vec<HookRow>) = native_execution_gate_edges(project)?;
    let cache: KeyCache<'py> = KeyCache::new(py)?;
    let edge_type: Bound<'py, PyAny> = record_class(py, RecordId::AttachedAuditGateEdge)?;
    let mut edges: Vec<Bound<'py, PyAny>> = Vec::with_capacity(gates.len());
    for GateRow {
        audit_name,
        target,
        gated,
        read,
    } in gates
    {
        edges.push(keyword_call(
            &edge_type,
            &[
                ("audit_name", PyString::new(py, &audit_name).into_any()),
                ("target", cache.key(&target)?),
                ("gated", cache.key(&gated)?),
                ("read", cache.key(&read)?),
            ],
        )?);
    }
    PyTuple::new(py, edges)
}

/// Edges from each hook read to the model that runs the hook.
#[pyfunction]
#[pyo3(signature = (*, project))]
fn hook_read_edges<'py>(
    py: Python<'py>,
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let (_, hooks): (Vec<GateRow>, Vec<HookRow>) = native_execution_gate_edges(project)?;
    let cache: KeyCache<'py> = KeyCache::new(py)?;
    let edge_type: Bound<'py, PyAny> = record_class(py, RecordId::HookReadEdge)?;
    let path_type: Bound<'py, PyAny> = py.import(PATHLIB_MODULE)?.getattr("Path")?;
    let mut edges: Vec<Bound<'py, PyAny>> = Vec::with_capacity(hooks.len());
    for HookRow {
        hook_name,
        gated,
        read,
        hook_type: kind,
        path,
    } in hooks
    {
        let hook_path: Bound<'py, PyAny> = match path {
            None => py.None().into_bound(py),
            Some(path) => path_type.call1((path,))?,
        };
        edges.push(keyword_call(
            &edge_type,
            &[
                ("hook_name", PyString::new(py, &hook_name).into_any()),
                ("gated", cache.key(&gated)?),
                ("read", cache.key(&read)?),
                (
                    "hook_type",
                    enum_from_value(py, RecordId::HookReadType, kind)?,
                ),
                ("hook_path", hook_path),
            ],
        )?);
    }
    PyTuple::new(py, edges)
}

/// The Python hooks attached to one model, in lifecycle order without repeats.
#[pyfunction]
#[pyo3(signature = (*, model))]
pub(crate) fn model_python_hook_names<'py>(
    py: Python<'py>,
    model: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let entry_type: Bound<'_, PyAny> = record_class(py, RecordId::PythonHookEntry)?;
    let values: Bound<'_, PyAny> = native_field(model, "config")?.getattr("values")?;
    let mut names: Vec<String> = Vec::new();
    for hook_key in MODEL_HOOK_KEYS {
        let entries: Bound<'_, PyAny> = mapping_get(&values, hook_key)?;
        if entries.is_instance(&entry_type)? {
            names.push(native_field(&entries, "name")?.extract()?);
        } else if entries.is_instance_of::<PyList>() || entries.is_instance_of::<PyTuple>() {
            for entry in entries.try_iter()? {
                let entry: Bound<'_, PyAny> = entry?;
                if entry.is_instance(&entry_type)? {
                    names.push(native_field(&entry, "name")?.extract()?);
                }
            }
        }
    }
    let mut unique: Vec<String> = Vec::with_capacity(names.len());
    for name in names {
        if !unique.contains(&name) {
            unique.push(name);
        }
    }
    PyTuple::new(py, unique)
}

/// The compiled graph key a typed model, source or seed reference names.
#[pyfunction]
pub(crate) fn sql_ref_key<'py>(
    py: Python<'py>,
    reference: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let resource_type: Bound<'py, PyAny> = enum_from_value(
        py,
        RecordId::CompiledResourceType,
        native_field(reference, "kind")?.getattr("value")?,
    )?;
    keyword_call(
        &record_class(py, RecordId::CompiledObjectKey)?,
        &[
            ("resource_type", resource_type),
            ("name", native_field(reference, "name")?),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(attached_audit_gate_edges, module)?)?;
    module.add_function(wrap_pyfunction!(hook_read_edges, module)?)?;
    module.add_function(wrap_pyfunction!(model_python_hook_names, module)?)?;
    module.add_function(wrap_pyfunction!(sql_ref_key, module)?)?;
    Ok(())
}
