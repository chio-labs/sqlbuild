//! Model-level cursor safety policy overrides over project configuration.

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::records::construct::{enum_from_value, record_class};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_get;
use crate::bindings::_helpers::records::ids::RecordId;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::PyString;
use pyo3::{pyfunction, wrap_pyfunction};

const POLICY_DISABLED: &str = "disabled";

/// The policy class, its distance field, and the model keys overriding distance and action.
struct PolicyFields {
    class: RecordId,
    distance: &'static str,
    distance_key: &'static str,
    action_key: &'static str,
}

const FUTURE_POLICY: PolicyFields = PolicyFields {
    class: RecordId::FutureCursorsConfig,
    distance: "max_distance",
    distance_key: "cursor_future_max_distance",
    action_key: "cursor_future_action",
};

const START_POLICY: PolicyFields = PolicyFields {
    class: RecordId::StartCursorsConfig,
    distance: "max_ahead",
    distance_key: "cursor_start_max_ahead",
    action_key: "cursor_start_max_action",
};

fn resolve_policy<'py>(
    model: &Bound<'py, PyAny>,
    project_config: &Bound<'py, PyAny>,
    fields: &PolicyFields,
) -> PyResult<Bound<'py, PyAny>> {
    let py = model.py();
    let class = record_class(py, fields.class)?;
    let configured = if project_config.is_truthy()? {
        project_config.clone()
    } else {
        class.call0()?
    };
    let values = native_field(&native_field(model, "config")?, "values")?;
    let raw_distance = mapping_get(&values, fields.distance_key)?;
    let raw_action = mapping_get(&values, fields.action_key)?;
    let mut distance = configured.getattr(fields.distance)?;
    if raw_distance.is_instance_of::<PyString>() {
        distance = if raw_distance.eq(POLICY_DISABLED)? {
            py.None().into_bound(py)
        } else {
            raw_distance
        };
    }
    let mut action = native_field(&configured, "action")?;
    if raw_action.is_instance_of::<PyString>() {
        action = enum_from_value(py, RecordId::FutureCursorAction, raw_action)?;
    }
    if distance.is_none() {
        return Ok(py.None().into_bound(py));
    }
    call_with(&class, &[(fields.distance, distance), ("action", action)])
}

/// The future-end policy for one model, model configuration taking precedence.
pub(crate) fn future_cursor_config<'py>(
    model: &Bound<'py, PyAny>,
    project_config: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    resolve_policy(model, project_config, &FUTURE_POLICY)
}

/// The automatic-start policy for one model, model configuration taking precedence.
pub(crate) fn start_cursor_config<'py>(
    model: &Bound<'py, PyAny>,
    project_config: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    resolve_policy(model, project_config, &START_POLICY)
}

/// Resolve future-end policy with model config taking precedence.
#[pyfunction]
#[pyo3(signature = (*, model, project_config))]
fn resolve_future_cursor_config<'py>(
    model: &Bound<'py, PyAny>,
    project_config: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    future_cursor_config(model, project_config)
}

/// Resolve automatic-start policy with model config taking precedence.
#[pyfunction]
#[pyo3(signature = (*, model, project_config))]
pub(crate) fn resolve_start_cursor_config<'py>(
    model: &Bound<'py, PyAny>,
    project_config: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    start_cursor_config(model, project_config)
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_future_cursor_config, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_start_cursor_config, module)?)
}
