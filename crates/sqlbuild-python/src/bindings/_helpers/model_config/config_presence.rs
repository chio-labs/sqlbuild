//! Recursive template and macro presence scans over authored Python config values.

use pyo3::prelude::{Bound, PyAny, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_model_config::config_presence::main::contains_macro_call::contains_macro_call;
use sqlbuild_model_config::config_presence::main::contains_template::contains_template;
use sqlbuild_model_config::config_presence::models::Presence;

use crate::bindings::_helpers::model_config::authored_nodes::PyNode;

fn answer(presence: Presence) -> Option<bool> {
    match presence {
        Presence::Present => Some(true),
        Presence::Absent => Some(false),
        Presence::Deferred => None,
    }
}

/// Return whether any nested string holds `${`, or `None` where Python must scan.
#[pyfunction]
fn config_contains_template(value: Bound<'_, PyAny>) -> Option<bool> {
    answer(contains_template(&PyNode(value)))
}

/// Return whether any nested string holds a macro call, or `None` where Python must scan.
#[pyfunction]
fn config_contains_macro_call(value: Bound<'_, PyAny>) -> Option<bool> {
    answer(contains_macro_call(&PyNode(value)))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(config_contains_template, module)?)?;
    module.add_function(wrap_pyfunction!(config_contains_macro_call, module)?)?;
    Ok(())
}
