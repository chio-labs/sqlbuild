//! The single seam between the compiler stages and the native frontier.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyDict;
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::frontier::stage_capture::write_stage_capture;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::native_host::user_code::UserCodeHost;
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::records::registry;

/// Produce the frontier object for `until`, capturing it on request.
#[pyfunction]
#[pyo3(signature = (**options))]
fn compile_frontier<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "compile_frontier",
        options,
        (&["until", "python_stage"], &["native_stage"]),
    )?;
    let until: Bound<'py, PyAny> = arguments.value("until")?;
    let result: Bound<'py, PyAny> = native_frontier(
        &until,
        &arguments.value("python_stage")?,
        &arguments.value("native_stage")?,
    )?;
    write_stage_capture(&until, &result)?;
    Ok(result)
}

/// The frontier object for `until`; stages not yet native run in Python.
fn native_frontier<'py>(
    until: &Bound<'py, PyAny>,
    python_stage: &Bound<'py, PyAny>,
    native_stage: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = until.py();
    if !native_stage.is_none() {
        return native_stage.call0();
    }
    let inputs_stage: Bound<'py, PyAny> =
        registry::class(py, RecordId::CompilerStage)?.getattr("COMPILE_PROJECT_INPUTS")?;
    if until.is(&inputs_stage) {
        return call_with(
            &host::entry(py, UserCodeHost::RunWithMacroBridge)?,
            &[("stage", python_stage.clone())],
        );
    }
    python_stage.call0()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(compile_frontier, module)?)
}
