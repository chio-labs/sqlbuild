//! Prominent warnings for applied future-end and automatic-start cursor safety.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::cursor::scalars::render_value;
use crate::bindings::_helpers::planner_resolution::values::string;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

const FUTURE_CAPPED_CODE: &str = "FUTURE_CURSOR_CAPPED";
const START_CAPPED_CODE: &str = "AUTOMATIC_START_CAPPED";

fn rendered(evidence: &Bound<'_, PyAny>, field: &str) -> PyResult<String> {
    render_value(&evidence.getattr(field)?)
}

/// Render a prominent warning for applied future cursor policy.
pub(crate) fn future_cap_message(bounds: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if bounds.is_none() {
        return Ok(None);
    }
    let evidence = bounds.getattr("future_safety")?;
    if evidence.is_none() {
        return Ok(None);
    }
    Ok(Some(format!(
        "FUTURE CURSOR CAPPED: discovered bounds ['{}', '{}'), applied bounds ['{}', '{}').",
        rendered(&evidence, "discovered_start")?,
        rendered(&evidence, "discovered_end")?,
        rendered(&evidence, "applied_start")?,
        rendered(&evidence, "applied_end")?,
    )))
}

/// Render a warning that distinguishes start recovery from future-end capping.
pub(crate) fn maximum_start_message(bounds: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if bounds.is_none() {
        return Ok(None);
    }
    let evidence = bounds.getattr("maximum_start_safety")?;
    if evidence.is_none() {
        return Ok(None);
    }
    let highest = evidence.getattr("highest_eligible_target_max")?;
    let highest = if highest.is_none() {
        "None".to_owned()
    } else {
        PyString::new(bounds.py(), &render_value(&highest)?)
            .repr()?
            .extract()?
    };
    Ok(Some(format!(
        "AUTOMATIC START CAPPED: physical target MAX '{}' exceeded horizon '{}'; highest \
         eligible target MAX={highest}, effective post-lookback start='{}', action={}, \
         input={}.{}.",
        rendered(&evidence, "physical_target_max")?,
        rendered(&evidence, "maximum_allowed_start")?,
        rendered(&evidence, "effective_start")?,
        evidence.getattr("action")?.getattr("value")?.str()?,
        evidence.getattr("target_relation")?.str()?,
        evidence.getattr("cursor_column")?.str()?,
    )))
}

/// `warnings` followed by the future-end and automatic-start warnings `bounds` carries.
pub(crate) fn with_cursor_safety_warnings<'py>(
    warnings: &Bound<'py, PyAny>,
    model_name: &Bound<'py, PyAny>,
    bounds: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = warnings.py();
    let mut all: Vec<Bound<'py, PyAny>> = warnings
        .try_iter()?
        .collect::<PyResult<Vec<Bound<'py, PyAny>>>>()?;
    for (message, code) in [
        (future_cap_message(bounds)?, FUTURE_CAPPED_CODE),
        (maximum_start_message(bounds)?, START_CAPPED_CODE),
    ] {
        let Some(message) = message else { continue };
        all.push(call_with(
            &imported(py, "sqlbuild._native", "PlanWarning")?,
            &[
                ("model_name", model_name.clone()),
                (
                    "severity",
                    imported(py, "sqlbuild._native", "WarningSeverity")?.getattr("WARNING")?,
                ),
                ("code", string(py, code)),
                ("message", string(py, &message)),
            ],
        )?);
    }
    Ok(PyTuple::new(py, all)?.into_any())
}

/// Render a prominent warning for applied future cursor policy.
#[pyfunction]
#[pyo3(signature = (bounds, /))]
fn future_cursor_cap_warning(bounds: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    future_cap_message(bounds)
}

/// Render a warning that distinguishes start recovery from future-end capping.
#[pyfunction]
#[pyo3(signature = (bounds, /))]
fn maximum_start_cap_warning(bounds: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    maximum_start_message(bounds)
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(future_cursor_cap_warning, module)?)?;
    module.add_function(wrap_pyfunction!(maximum_start_cap_warning, module)?)
}
