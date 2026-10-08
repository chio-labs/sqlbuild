//! Native config errors handed to Python, which raises them as the Python stages would.

use pyo3::Py;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use sqlbuild_model_config::errors::{ConfigError, ErrorClass};

use crate::bindings::_helpers::model_config::errors::NativeConfigError;

const COMPILE_INPUT_CLASS: &str = "compile_input";
const CONFIG_VALUE_TYPE_CLASS: &str = "config_value_type";
const RESOURCE_IDENTITY_CLASS: &str = "resource_identity";
const DISCOVERY_CONFLICT_CLASS: &str = "discovery_conflict";

/// Wrap `error` for Python.
pub(crate) fn native_config_error(
    py: Python<'_>,
    error: ConfigError,
) -> PyResult<Py<NativeConfigError>> {
    let class_name = match error.class {
        ErrorClass::CompileInput => COMPILE_INPUT_CLASS,
        ErrorClass::ConfigValueType => CONFIG_VALUE_TYPE_CLASS,
        ErrorClass::ResourceIdentity => RESOURCE_IDENTITY_CLASS,
        ErrorClass::DiscoveryConflict => DISCOVERY_CONFLICT_CLASS,
    };
    Py::new(
        py,
        NativeConfigError {
            class_name,
            message: error.message,
            code: error.code,
            help: error.help,
            key: error.key,
        },
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeConfigError>()?;
    Ok(())
}
