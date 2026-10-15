//! Register Dagster invocation assembly and event planning.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::wrap_pyfunction;

use crate::bindings::_helpers::dagster_invocation::{arguments, failures, results};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(arguments::dagster_cli_arguments, module)?)?;
    module.add_function(wrap_pyfunction!(
        arguments::dagster_selector_log_lines,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(results::dagster_payload_results, module)?)?;
    module.add_function(wrap_pyfunction!(
        results::dagster_integration_results,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        results::dagster_selected_asset_results,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        results::dagster_execution_payload,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(failures::dagster_failure, module)?)?;
    module.add_function(wrap_pyfunction!(failures::dagster_live_failure, module)?)
}
