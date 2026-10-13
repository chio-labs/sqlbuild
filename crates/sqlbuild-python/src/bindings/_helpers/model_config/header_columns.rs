//! Authored MODEL and SCHEMA columns parsed natively into contract columns.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_model_config::errors::{ConfigError, ErrorClass};
use sqlbuild_model_config::header_metadata::main::parse_schema_columns::parse_schema_columns as parse_columns;
use sqlbuild_model_config::header_metadata::models::ColumnRequest;

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::model_config::authored_nodes::PyNode;
use crate::bindings::_helpers::model_config::config_errors::native_config_error;
use crate::bindings::_helpers::model_config::header_metadata::{ContractClasses, column_tuple};

const CONTRACT_CLASSES_MODULE: &str =
    "sqlbuild.compiler.model_config.main._native_contract_classes";
const CONFIG_ERROR_MODULE: &str = "sqlbuild.compiler.model_config.main._native_config_error";
const DISCOVERY_ERRORS_MODULE: &str = "sqlbuild.compiler.discovery.exceptions";
const DECLARATION_ERROR_CLASS: &str = "DeclarationParseError";

/// `(file_path, label)`: the path and label every message names.
pub(crate) type ColumnSite<'a> = (&'a str, &'a str);
/// `(require_columns, allow_migrate_from, declaration_errors)`.
pub(crate) type ColumnOptions = (bool, bool, bool);

/// The `SchemaColumn` tuple of one authored columns mapping, raising Python's error for it.
pub(crate) fn schema_columns<'py>(
    raw_columns: &Bound<'py, PyAny>,
    site: ColumnSite<'_>,
    options: ColumnOptions,
    column_locations: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = raw_columns.py();
    let (path, label) = site;
    let (require_columns, allow_migrate_from, declaration_errors) = options;
    let request = ColumnRequest {
        path,
        label,
        require_columns,
        allow_migrate_from,
    };
    let columns = parse_columns(&PyNode(raw_columns.clone()), request)
        .map_err(|error| raised(py, error, declaration_errors))?;
    let classes: ContractClasses<'py> =
        imported(py, CONTRACT_CLASSES_MODULE, "native_contract_classes")?
            .call0()?
            .extract()?;
    column_tuple(py, &classes, &columns, column_locations)
}

/// Parse one MODEL or SCHEMA `columns` mapping into contract columns.
#[pyfunction]
fn parse_schema_columns<'py>(
    raw_columns: Bound<'py, PyAny>,
    site: (String, String),
    options: ColumnOptions,
    column_locations: Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyTuple>> {
    compiler_guard(|| schema_columns(&raw_columns, (&site.0, &site.1), options, &column_locations))
}

/// A plain parse error as `DeclarationParseError` when asked; every other error as Python raises it.
fn raised(py: Python<'_>, error: ConfigError, declaration_errors: bool) -> PyErr {
    let built = (|| {
        if declaration_errors && error.class == ErrorClass::CompileInput {
            return imported(py, DISCOVERY_ERRORS_MODULE, DECLARATION_ERROR_CLASS)?
                .call1((error.message,));
        }
        let native = native_config_error(py, error)?.into_bound(py).into_any();
        call_with(
            &imported(py, CONFIG_ERROR_MODULE, "native_config_error")?,
            &[("error", native)],
        )
    })();
    match built {
        Ok(instance) => PyErr::from_value(instance),
        Err(failure) => failure,
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_schema_columns, module)?)
}
