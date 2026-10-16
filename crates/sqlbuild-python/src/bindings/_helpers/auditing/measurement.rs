//! A measured value's audit outcome under its sample and threshold policy.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::auditing::main::evaluate_measurement::evaluate_measurement as evaluate;
use sqlbuild_analysis::auditing::models::{MeasurementOutcome, Thresholds};

use crate::bindings::_helpers::auditing::identity::thresholds as read_thresholds;
use crate::bindings::_helpers::records::ids::ErrorId;
use crate::bindings::_helpers::records::registry;

const AUDITING_TYPES_MODULE: &str = "sqlbuild.compiler.auditing.types";

fn measurement_error(py: Python<'_>, message: &str) -> PyErr {
    match registry::error(py, ErrorId::MeasurementAudit).and_then(|class| class.call1((message,))) {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// The canonical outcome for one finite measured value.
#[pyfunction]
#[pyo3(signature = (*, measured_value, sample_count, minimum_samples, thresholds))]
fn evaluate_measurement<'py>(
    measured_value: f64,
    sample_count: Option<i128>,
    minimum_samples: Option<i128>,
    thresholds: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = thresholds.py();
    let thresholds: Thresholds = read_thresholds(thresholds)?.unwrap_or_default();
    let outcome: MeasurementOutcome =
        evaluate(measured_value, (sample_count, minimum_samples), thresholds)
            .map_err(|message| measurement_error(py, message))?;
    let member: &str = match outcome {
        MeasurementOutcome::Pass => "PASS",
        MeasurementOutcome::Warn => "WARN",
        MeasurementOutcome::Error => "ERROR",
        MeasurementOutcome::Insufficient => "INSUFFICIENT",
    };
    py.import(AUDITING_TYPES_MODULE)?
        .getattr("AuditOutcome")?
        .getattr(member)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(evaluate_measurement, module)?)?;
    Ok(())
}
