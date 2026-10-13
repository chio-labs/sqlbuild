//! Cost telemetry that never changes a build result: failures become a logged warning.

use std::path::PathBuf;

use pyo3::exceptions::PyException;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyTypeMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::cost_report::main::format_cost_breakdown::format_cost_breakdown;
use sqlbuild_core::cost_report::models::BreakdownOptions;

use crate::bindings::_helpers::cost_report::records::cost_run;
use crate::bindings::_helpers::cost_report::store;

const LOGGER_NAME: &str = "sqlbuild.cli.commands._helpers.cost.collection";
const BUILD_BREAKDOWN_LIMIT: usize = 5;
const FALLBACK_TERMINAL_COLUMNS: usize = 100;

/// Log the failure with its traceback, as `_LOGGER.exception` inside the handler did.
fn log_failure(py: Python<'_>, message: &str, error: &PyErr) -> PyResult<()> {
    let logger: Bound<'_, PyAny> = py
        .import("logging")?
        .call_method1("getLogger", (LOGGER_NAME,))?;
    let keywords: Bound<'_, PyDict> = PyDict::new(py);
    keywords.set_item("exc_info", error.value(py))?;
    logger.call_method("exception", (message,), Some(&keywords))?;
    Ok(())
}

fn error_type(py: Python<'_>, error: &PyErr) -> PyResult<String> {
    Ok(error.get_type(py).name()?.to_string())
}

/// `_write_warning`: a warning line on the build's stream; its own failure is only logged.
fn warn(output_stream: &Bound<'_, PyAny>, message: &str) -> PyResult<()> {
    let written: PyResult<()> = output_stream
        .call_method1("write", (format!("\nWARNING: {message}\n"),))
        .and_then(|_| output_stream.call_method0("flush"))
        .map(|_| ());
    match written {
        Ok(()) => Ok(()),
        Err(error) => log_failure(
            output_stream.py(),
            "automatic run-cost warning output failed",
            &error,
        ),
    }
}

/// Persist a run's cost artifact; any failure is logged and reported as a warning.
#[pyfunction]
#[pyo3(signature = (*, project_dir, record, output_stream, stage))]
fn persist_cost_run(
    project_dir: PathBuf,
    record: &Bound<'_, PyAny>,
    output_stream: &Bound<'_, PyAny>,
    stage: &str,
) -> PyResult<()> {
    let py: Python<'_> = record.py();
    let Err(error) = cost_run(record).and_then(|run| store::write(py, &project_dir, &run)) else {
        return Ok(());
    };
    log_failure(py, &format!("automatic run-cost {stage} failed"), &error)?;
    warn(
        output_stream,
        &format!(
            "Cost telemetry failed during {stage} ({}); build result unchanged.",
            error_type(py, &error)?
        ),
    )
}

fn breakdown_text(py: Python<'_>, record: &Bound<'_, PyAny>, use_color: bool) -> PyResult<String> {
    let terminal_width: usize = py
        .import("shutil")?
        .call_method1("get_terminal_size", ((FALLBACK_TERMINAL_COLUMNS, 24),))?
        .getattr("columns")?
        .extract()?;
    Ok(format_cost_breakdown(
        &cost_run(record)?,
        BreakdownOptions {
            use_color,
            limit: Some(BUILD_BREAKDOWN_LIMIT),
            terminal_width,
            show_run_id: false,
        },
    ))
}

/// Write the build's cost breakdown; an `Exception` while rendering becomes a warning.
#[pyfunction]
#[pyo3(signature = (*, record, output_stream, use_color))]
fn write_build_cost_breakdown(
    record: &Bound<'_, PyAny>,
    output_stream: &Bound<'_, PyAny>,
    use_color: bool,
) -> PyResult<()> {
    let py: Python<'_> = record.py();
    let written: PyResult<()> = breakdown_text(py, record, use_color)
        .and_then(|text| output_stream.call_method1("write", (format!("\n{text}\n"),)))
        .and_then(|_| output_stream.call_method0("flush"))
        .map(|_| ());
    let Err(error) = written else {
        return Ok(());
    };
    if !error.is_instance_of::<PyException>(py) {
        return Err(error);
    }
    log_failure(py, "automatic run-cost output failed", &error)?;
    warn(
        output_stream,
        &format!(
            "Cost telemetry failed during output rendering ({}); build result unchanged.",
            error_type(py, &error)?
        ),
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(persist_cost_run, module)?)?;
    module.add_function(wrap_pyfunction!(write_build_cost_breakdown, module)?)
}
