//! Register scenario planning bindings.

use crate::bindings::_helpers::planner_scenario::{cli, graph, relations};
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::wrap_pyfunction;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(graph::plan_scenario_graph, module)?)?;
    module.add_function(wrap_pyfunction!(
        relations::build_scenario_relation_plan,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(cli::build_cli_scenario_plan, module)?)?;
    Ok(())
}
