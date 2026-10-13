//! Migration event IDs and the SQL that appends and looks up one event row.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyString};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_state::events::errors::StateSqlError;
use sqlbuild_state::events::main::column_migration_event_id::column_migration_event_id;
use sqlbuild_state::events::main::event_exists_sql::event_exists_sql;
use sqlbuild_state::events::main::event_insert_sql::event_insert_sql;
use sqlbuild_state::events::main::migration_event_id::migration_event_id;
use sqlbuild_state::events::main::old_name_view_event_id::old_name_view_event_id;
use sqlbuild_state::events::models::{EventRelation, StateCell, StateColumnType, StateValue};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::imported;
use crate::bindings::_helpers::state_rows::timestamps::{date_time_typed, presumed_utc};

const SQL_VALUES_EXCEPTIONS: &str = "sqlbuild.sql_values.exceptions";
const STRING_TYPE: &str = "string";
const TEXT_TIMESTAMP_TYPE: &str = "text_timestamp";

fn emit_error(error: JsonEmitError) -> PyErr {
    PyValueError::new_err(format!("{error:?}"))
}

fn relation(value: &Bound<'_, PyAny>) -> PyResult<EventRelation> {
    Ok(EventRelation {
        database: value.getattr("database")?.extract()?,
        schema: value.getattr("schema")?.extract()?,
        name: value.getattr("name")?.extract()?,
    })
}

/// The content-addressed ID for one migration performed by one run.
#[pyfunction(name = "deterministic_migration_event_id")]
#[pyo3(signature = (*, run_id, target_name, origin, destination))]
fn migration_id(
    run_id: &str,
    target_name: Option<&str>,
    origin: &Bound<'_, PyAny>,
    destination: &Bound<'_, PyAny>,
) -> PyResult<String> {
    migration_event_id(
        (run_id, target_name),
        &relation(origin)?,
        &relation(destination)?,
    )
    .map_err(emit_error)
}

/// The content-addressed ID for one column rename performed by one run.
#[pyfunction(name = "deterministic_column_migration_event_id")]
#[pyo3(signature = (**request))]
fn column_id(request: Option<&Bound<'_, PyDict>>) -> PyResult<String> {
    let request = Request::new("deterministic_column_migration_event_id", request)?;
    let run_id: String = request.get("run_id")?.extract()?;
    let target_name: Option<String> = request.get("target_name")?.extract()?;
    let origin_column: String = request.get("origin_column")?.extract()?;
    let destination_column: String = request.get("destination_column")?.extract()?;
    column_migration_event_id(
        (&run_id, target_name.as_deref()),
        &relation(&request.get("relation")?)?,
        (&origin_column, &destination_column),
    )
    .map_err(emit_error)
}

/// The content-addressed ID of one old-name step of one recorded move.
#[pyfunction(name = "deterministic_old_name_view_event_id")]
#[pyo3(signature = (*, event_type, migration_event_id))]
fn old_name_id(event_type: &Bound<'_, PyAny>, migration_event_id: &str) -> PyResult<String> {
    let event_type: String = event_type.getattr("value")?.extract()?;
    old_name_view_event_id(&event_type, migration_event_id).map_err(emit_error)
}

/// The lookup that makes an append-only event write idempotent.
#[pyfunction(name = "render_event_exists_sql")]
#[pyo3(signature = (*, table, event_id))]
fn exists_sql(table: &str, event_id: &str) -> String {
    event_exists_sql(table, event_id)
}

fn state_value(value: &Bound<'_, PyAny>, column_type: StateColumnType) -> PyResult<StateValue> {
    if value.is_none() {
        return Ok(StateValue::Null);
    }
    if let Ok(text) = value.downcast::<PyString>() {
        return Ok(StateValue::Text(text.extract()?));
    }
    if column_type == StateColumnType::TextTimestamp && date_time_typed(value)? {
        return Ok(StateValue::UtcTimestamp(presumed_utc(value)?));
    }
    Ok(StateValue::Other)
}

fn column_type(declared: &Bound<'_, PyAny>) -> PyResult<StateColumnType> {
    let name: String = declared.str()?.extract()?;
    match name.as_str() {
        STRING_TYPE => Ok(StateColumnType::String),
        TEXT_TIMESTAMP_TYPE => Ok(StateColumnType::TextTimestamp),
        _ => Err(PyValueError::new_err(format!(
            "migration event columns are string or text timestamps, not {name}"
        ))),
    }
}

/// One append-only event row as `INSERT ... VALUES` with typed literals.
#[pyfunction(name = "render_event_insert_sql")]
#[pyo3(signature = (*, table, columns, column_types, values))]
fn insert_sql(
    table: &str,
    columns: Vec<String>,
    column_types: &Bound<'_, PyAny>,
    values: Vec<Bound<'_, PyAny>>,
) -> PyResult<String> {
    if columns.len() != values.len() {
        return Err(PyValueError::new_err(
            "event columns and values must have the same length",
        ));
    }
    let mut cells: Vec<StateCell> = Vec::with_capacity(columns.len());
    for (column, value) in columns.into_iter().zip(&values) {
        let column_type: StateColumnType = column_type(&column_types.get_item(&column)?)?;
        let converted: PyResult<StateValue> = state_value(value, column_type);
        let value: StateValue = match converted {
            Ok(value) => value,
            Err(error) => {
                event_insert_sql(table, &cells).map_err(rendering_error(value.py()))?;
                return Err(error);
            }
        };
        cells.push(StateCell {
            column,
            column_type,
            value,
        });
    }
    event_insert_sql(table, &cells).map_err(rendering_error(column_types.py()))
}

/// `SqlValueRenderingError(message)` for an ill-typed value.
fn rendering_error(py: Python<'_>) -> impl Fn(StateSqlError) -> PyErr + '_ {
    move |error: StateSqlError| {
        let raised = imported(py, SQL_VALUES_EXCEPTIONS, "SqlValueRenderingError")
            .and_then(|class| class.call1((error.0,)));
        match raised {
            Ok(exception) => PyErr::from_value(exception),
            Err(failure) => failure,
        }
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(migration_id, module)?)?;
    module.add_function(wrap_pyfunction!(column_id, module)?)?;
    module.add_function(wrap_pyfunction!(old_name_id, module)?)?;
    module.add_function(wrap_pyfunction!(exists_sql, module)?)?;
    module.add_function(wrap_pyfunction!(insert_sql, module)?)?;
    Ok(())
}
