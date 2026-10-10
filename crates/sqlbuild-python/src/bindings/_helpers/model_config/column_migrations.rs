//! Column renames validated natively, raised by Python as the attachment raises them.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyStringMethods};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_model_config::errors::ConfigError;
use sqlbuild_model_config::model_validation::main::validate_column_migrations::validate_column_migrations;
use sqlbuild_model_config::model_validation::models::ColumnMigration;

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::model_config::config_errors::native_config_error;

const MATERIALIZED_KEY: &str = "materialized";
const MIGRATE_FROM_KEY: &str = "migrate_from";

/// The first column-rename problem for a model with these config values, if any.
pub(crate) fn column_migration_error(
    model_name: &str,
    values: &Bound<'_, PyDict>,
    columns: &[ColumnMigration],
) -> PyResult<Option<ConfigError>> {
    if columns.iter().all(|column| column.migrate_from.is_none()) {
        return Ok(None);
    }
    let materialized: Option<String> = match values.get_item(MATERIALIZED_KEY)? {
        None => None,
        Some(value) if value.is_none() => None,
        Some(value) => match value.downcast::<PyString>() {
            Ok(text) => Some(text.to_str()?.to_owned()),
            Err(_) => return Ok(Some(ConfigError::config_value_type(MATERIALIZED_KEY))),
        },
    };
    let model_migrates: bool = values
        .get_item(MIGRATE_FROM_KEY)?
        .is_some_and(|value| !value.is_none());
    Ok(
        validate_column_migrations(model_name, materialized.as_deref(), model_migrates, columns)
            .err(),
    )
}

/// `None`, or the native error for the model's first column-rename problem.
#[pyfunction]
fn column_migration_problem<'py>(
    py: Python<'py>,
    model_name: &str,
    values: Bound<'py, PyDict>,
    columns: Vec<(String, Option<String>)>,
) -> PyResult<Bound<'py, PyAny>> {
    let columns: Vec<ColumnMigration> = columns
        .into_iter()
        .map(|(name, migrate_from)| ColumnMigration { name, migrate_from })
        .collect();
    compiler_guard(
        || match column_migration_error(model_name, &values, &columns)? {
            Some(error) => Ok(native_config_error(py, error)?.into_bound(py).into_any()),
            None => Ok(py.None().into_pyobject(py)?.into_any()),
        },
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(column_migration_problem, module)?)
}
