//! Process-local statement-ledger failure tracking for the active build.

use std::collections::HashMap;
use std::sync::{Mutex, MutexGuard, PoisonError};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::PyTypeMethods;
use pyo3::{pyclass, pymethods};

const HEALTH_ATTRIBUTE: &str = "COST_TELEMETRY_HEALTH";

static LEDGER_FAILURES: Mutex<Option<HashMap<String, String>>> = Mutex::new(None);

fn failures() -> MutexGuard<'static, Option<HashMap<String, String>>> {
    LEDGER_FAILURES
        .lock()
        .unwrap_or_else(PoisonError::into_inner)
}

/// Remember the first ledger failure of `run_id` by its exception type name.
pub(crate) fn mark_ledger_failure(run_id: String, error: &Bound<'_, PyAny>) -> PyResult<()> {
    let name: String = error.get_type().name()?.extract()?;
    failures()
        .get_or_insert_with(HashMap::new)
        .entry(run_id)
        .or_insert(name);
    Ok(())
}

/// The ledger failure recorded for `run_id`, forgetting it.
pub(crate) fn consume_ledger_failure(run_id: &str) -> Option<String> {
    failures().as_mut()?.remove(run_id)
}

/// The process-wide ledger failure tracker, exposed as `COST_TELEMETRY_HEALTH`.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct CostTelemetryHealth;

#[pymethods]
impl CostTelemetryHealth {
    #[pyo3(signature = (*, run_id, error))]
    fn mark_ledger_failure(&self, run_id: String, error: &Bound<'_, PyAny>) -> PyResult<()> {
        mark_ledger_failure(run_id, error)
    }

    #[pyo3(signature = (*, run_id))]
    fn consume_ledger_failure(&self, run_id: &str) -> Option<String> {
        consume_ledger_failure(run_id)
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<CostTelemetryHealth>()?;
    module.add(HEALTH_ATTRIBUTE, CostTelemetryHealth)
}
