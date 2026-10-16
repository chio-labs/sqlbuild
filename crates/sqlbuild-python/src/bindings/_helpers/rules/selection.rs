//! The active rule codes of a rules configuration and its custom rules, resolved natively.

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::PyDict;
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_rules::rules::main::selected_codes::selected_codes_json;

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::records::ids::ErrorId;
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::rules::constants::RULES_NATIVE_API_VERSION;

const DATACLASSES_MODULE: &str = "dataclasses";
const JSON_MODULE: &str = "json";
const BUILTINS_MODULE: &str = "builtins";

/// The selected built-in and custom rule codes; invalid configuration raises `RulesError`.
#[pyfunction]
#[pyo3(signature = (*, config, custom_payloads))]
pub(crate) fn selected_rule_codes(
    config: &Bound<'_, PyAny>,
    custom_payloads: &Bound<'_, PyAny>,
) -> PyResult<Vec<String>> {
    let py: Python<'_> = config.py();
    let request: Bound<'_, PyDict> = PyDict::new(py);
    request.set_item("version", RULES_NATIVE_API_VERSION)?;
    request.set_item(
        "config",
        py.import(DATACLASSES_MODULE)?
            .getattr("asdict")?
            .call1((config,))?,
    )?;
    request.set_item("custom_rules", custom_payloads)?;
    let arguments: Bound<'_, PyDict> = PyDict::new(py);
    arguments.set_item("sort_keys", true)?;
    arguments.set_item("default", py.import(BUILTINS_MODULE)?.getattr("str")?)?;
    let encoded: String = match py
        .import(JSON_MODULE)?
        .getattr("dumps")?
        .call((request,), Some(&arguments))
    {
        Ok(encoded) => encoded.extract()?,
        Err(error)
            if error.is_instance_of::<PyValueError>(py)
                || error.is_instance_of::<PyTypeError>(py) =>
        {
            let message: String = error.value(py).str()?.extract()?;
            return Err(rules_error(py, &message, Some(error)));
        }
        Err(error) => return Err(error),
    };
    let selected: Result<String, String> = compiler_guard(|| Ok(selected_codes_json(&encoded)))?;
    let codes: String = selected.map_err(|message| rules_error(py, &message, None))?;
    serde_json::from_str::<Vec<String>>(&codes).map_err(|_| {
        rules_error(
            py,
            "native rules engine returned invalid selected rule codes",
            None,
        )
    })
}

/// Whether `code` is selected and not ignored by the configuration's prefixes.
#[pyfunction]
#[pyo3(signature = (*, config, code))]
fn rule_selected(config: &Bound<'_, PyAny>, code: &str) -> PyResult<bool> {
    let matches = |field: &str| -> PyResult<bool> {
        for selector in config.getattr(field)?.try_iter()? {
            let selector: String = selector?.extract()?;
            if code.starts_with(&selector) {
                return Ok(true);
            }
        }
        Ok(false)
    };
    Ok(matches("select")? && !matches("ignore")?)
}

/// `RulesError(message)`, caused by `cause` when given.
pub(crate) fn rules_error(py: Python<'_>, message: &str, cause: Option<PyErr>) -> PyErr {
    let raised = || -> PyResult<PyErr> {
        let error: Bound<'_, PyAny> = registry::error(py, ErrorId::Rules)?.call1((message,))?;
        Ok(PyErr::from_value(error))
    };
    let error: PyErr = raised().unwrap_or_else(|error| error);
    if let Some(cause) = cause {
        error.set_cause(py, Some(cause));
    }
    error
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(selected_rule_codes, module)?)?;
    module.add_function(wrap_pyfunction!(rule_selected, module)?)
}
