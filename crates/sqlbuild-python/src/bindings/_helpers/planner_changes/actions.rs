//! Per-model actions from each model's own change, and the incremental replacement predicate.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::records::registry;

const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const INCREMENTAL_MATERIALIZATION: &str = "incremental";
const CREATE_TABLE_ACTION: &str = "create_table";

/// Each selected model's change with the backfill its own `replay_on_change` decided.
#[pyfunction]
#[pyo3(signature = (*, scope, changes))]
pub(crate) fn resolve_model_actions<'py>(
    scope: &Bound<'py, PyAny>,
    changes: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = scope.py();
    let model_kind: Bound<'py, PyAny> =
        imported(py, COMPILE_TYPES_MODULE, "CompiledResourceType")?.getattr("MODEL")?;
    let action_class: Bound<'py, PyAny> = registry::class(py, RecordId::ResolvedModelAction)?;
    let selected: Bound<'py, PyAny> = scope.getattr("selected_keys")?;
    let models_by_name: Bound<'py, PyAny> = scope.getattr("models_by_name")?;
    let model_changes: Bound<'py, PyAny> = changes.getattr("models")?;
    let resolved: Bound<'py, PyDict> = PyDict::new(py);
    for key in scope.getattr("execution_order")?.try_iter()? {
        let key: Bound<'py, PyAny> = key?;
        if !selected.contains(&key)? || !key.getattr("resource_type")?.eq(&model_kind)? {
            continue;
        }
        let name: Bound<'py, PyAny> = key.getattr("name")?;
        let change: Bound<'py, PyAny> = model_changes.call_method1("get", (&name,))?;
        if !models_by_name.contains(&name)? || change.is_none() {
            continue;
        }
        let backfill: Bound<'py, PyAny> = change.getattr("backfill")?;
        resolved.set_item(
            name,
            call_with(&action_class, &[("change", change), ("backfill", backfill)])?,
        )?;
    }
    call_with(
        &registry::class(py, RecordId::PlannerResolvedActions)?,
        &[("models", resolved.into_any())],
    )
}

/// Incremental replacements, whose bounds must ignore the destination maximum.
#[pyfunction]
#[pyo3(signature = (*, materialization_type, action))]
pub(crate) fn replaces_incremental_relation(materialization_type: &str, action: &str) -> bool {
    materialization_type == INCREMENTAL_MATERIALIZATION && action == CREATE_TABLE_ACTION
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_model_actions, module)?)?;
    module.add_function(wrap_pyfunction!(replaces_incremental_relation, module)?)
}
