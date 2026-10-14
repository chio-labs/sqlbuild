//! Create, read and append SQL of migration state tables, and stored rows decoded to events.

use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_state::events::constants::TIMESTAMP_COLUMNS;
use sqlbuild_state::events::main::column_aliases_json::column_aliases_json;
use sqlbuild_state::events::main::decoded_column_aliases::decoded_column_aliases;
use sqlbuild_state::events::main::decoded_grants::decoded_grants;
use sqlbuild_state::events::main::event_exists_sql::event_exists_sql;
use sqlbuild_state::events::main::event_read_sql::event_read_sql;
use sqlbuild_state::events::main::grants_json::grants_json;
use sqlbuild_state::events::main::readable_columns::readable_columns;

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::cursor::values::DATETIME_MODULE;
use crate::bindings::_helpers::state_rows::constants::{
    MIGRATION_MODELS, MIGRATION_TYPES, SQL_VALUE_TYPES, STATE_TABLE_DDL,
};
use crate::bindings::_helpers::state_rows::events::typed_insert_sql;
use crate::bindings::_helpers::state_rows::migration_objects::{
    layout, qualified_table, state_error,
};
use crate::bindings::_helpers::state_rows::models::{EventTable, EventTableLayout};
use crate::bindings::_helpers::state_rows::timestamps::date_time_typed;

/// DDL that creates one migration state table when it is missing.
#[pyfunction(name = "render_migration_state_create_sql")]
#[pyo3(signature = (**request))]
fn create_sql<'py>(request: Option<&Bound<'py, PyDict>>) -> PyResult<Bound<'py, PyAny>> {
    let request = Request::new("render_migration_state_create_sql", request)?;
    let py: Python<'py> = request.py();
    let layout: EventTableLayout = layout(&request.get("kind")?.extract::<String>()?)?;
    let table: String = qualified_table(
        &layout,
        &request.get("render_qualified_name")?,
        (request.get("database")?, request.get("schema")?),
    )?;
    let value_types: Bound<'py, PyAny> = imported(py, SQL_VALUE_TYPES, "StateSqlValueType")?;
    let column_types: Bound<'py, PyDict> = PyDict::new(py);
    for column in layout.columns {
        let member: &str = if TIMESTAMP_COLUMNS.contains(column) {
            "TEXT_TIMESTAMP"
        } else {
            "STRING"
        };
        column_types.set_item(*column, value_types.getattr(member)?)?;
    }
    call_with(
        &imported(py, STATE_TABLE_DDL, "render_state_table_create_sql")?,
        &[
            ("qualified_name", PyString::new(py, &table).into_any()),
            ("columns", PyTuple::new(py, layout.columns)?.into_any()),
            ("column_types", column_types.into_any()),
            ("required_columns", PyFrozenSet::empty(py)?.into_any()),
            (
                "render_framework_type",
                request.get("render_framework_type")?,
            ),
        ],
    )
}

/// The SQL reading every stored event of one schema, and the columns it selects.
#[pyfunction(name = "render_migration_event_read_sql")]
#[pyo3(signature = (**request))]
fn read_sql<'py>(request: Option<&Bound<'py, PyDict>>) -> PyResult<(String, Bound<'py, PyTuple>)> {
    let request = Request::new("render_migration_event_read_sql", request)?;
    let layout: EventTableLayout = layout(&request.get("kind")?.extract::<String>()?)?;
    let stored: Option<Vec<String>> = match request.optional("stored_columns")? {
        Some(stored) if !stored.is_none() => Some(stored.extract()?),
        _ => None,
    };
    let columns: Vec<&str> = match &stored {
        Some(stored) => readable_columns(layout.columns, stored),
        None => layout.columns.to_vec(),
    };
    let table: String = qualified_table(
        &layout,
        &request.get("render_qualified_name")?,
        (request.get("database")?, request.get("schema")?),
    )?;
    Ok((
        event_read_sql(&table, &columns),
        PyTuple::new(request.py(), columns)?,
    ))
}

fn optional<'py>(value: Bound<'py, PyAny>, attribute: &str) -> PyResult<Bound<'py, PyAny>> {
    if value.is_none() {
        Ok(value)
    } else {
        value.getattr(attribute)
    }
}

fn text<'py>(py: Python<'py>, value: Option<String>) -> Bound<'py, PyAny> {
    match value {
        Some(value) => PyString::new(py, &value).into_any(),
        None => py.None().into_bound(py),
    }
}

fn row_values<'py>(
    table: EventTable,
    event: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = event.py();
    let field = |name: &str| event.getattr(name);
    let relation = |name: &str| -> PyResult<[Bound<'py, PyAny>; 3]> {
        let relation: Bound<'py, PyAny> = event.getattr(name)?;
        Ok([
            relation.getattr("database")?,
            relation.getattr("schema")?,
            relation.getattr("name")?,
        ])
    };
    let mut values: Vec<Bound<'py, PyAny>> = vec![field("event_id")?, field("target_name")?];
    match table {
        EventTable::Model => {
            values.push(field("origin_model")?);
            values.extend(relation("origin")?);
            values.push(field("destination_model")?);
            values.extend(relation("destination")?);
            values.push(field("origin_version_hash")?);
        }
        EventTable::Column => {
            values.push(field("model_name")?);
            values.extend(relation("relation")?);
            values.push(field("origin_column")?);
            values.push(field("destination_column")?);
        }
        EventTable::OldName => {
            values.push(field("event_type")?.getattr("value")?);
            values.push(field("migration_event_id")?);
            values.push(field("destination_model")?);
            values.extend(relation("old")?);
            values.extend(relation("new")?);
            values.push(field("view_retention")?);
            values.push(field("archive_name")?);
            let aliases: Vec<(String, String)> = field("column_aliases")?.extract()?;
            let encoded = column_aliases_json(&aliases).map_err(json_error)?;
            values.push(text(py, encoded));
            let grants: Option<Vec<String>> = field("grants_copied")?.extract()?;
            values.push(text(
                py,
                grants_json(grants.as_deref()).map_err(json_error)?,
            ));
            values.push(field("view_sql")?);
            values.push(field("expires_at")?);
            values.push(optional(field("drop_reason")?, "value")?);
            values.push(field("run_id")?);
            values.push(field("created_at")?);
            return Ok(values);
        }
    }
    values.push(field("discovery")?.getattr("value")?);
    values.push(field("decision")?.getattr("value")?);
    values.push(field("run_id")?);
    values.push(field("created_at")?);
    Ok(values)
}

fn json_error(error: sqlbuild_core::json::errors::JsonEmitError) -> PyErr {
    PyValueError::new_err(format!("{error:?}"))
}

/// The idempotency lookup and the insert that append one event to its schema's state table.
#[pyfunction(name = "render_migration_event_write_sql")]
#[pyo3(signature = (*, kind, event, render_qualified_name))]
fn write_sql<'py>(
    kind: &str,
    event: &Bound<'py, PyAny>,
    render_qualified_name: &Bound<'py, PyAny>,
) -> PyResult<(String, String)> {
    let py: Python<'py> = event.py();
    let layout: EventTableLayout = layout(kind)?;
    let relation: Bound<'py, PyAny> = event.getattr(layout.relation_attribute)?;
    let schema: Bound<'py, PyAny> = relation.getattr("schema")?;
    if schema.is_none() {
        return Err(state_error(py, layout.event_message));
    }
    let table: String = qualified_table(
        &layout,
        render_qualified_name,
        (relation.getattr("database")?, schema),
    )?;
    let event_id: String = event.getattr("event_id")?.extract()?;
    let values: Vec<Bound<'py, PyAny>> = row_values(layout.table, event)?;
    let insert: String = typed_insert_sql(py, &table, (layout.columns, &values))?;
    Ok((event_exists_sql(&table, &event_id), insert))
}

/// One stored row keyed by the columns its query selected.
struct StoredRow<'a, 'py> {
    columns: &'a [String],
    values: Vec<Bound<'py, PyAny>>,
}

impl<'py> StoredRow<'_, 'py> {
    fn get(&self, column: &str) -> Option<&Bound<'py, PyAny>> {
        self.columns
            .iter()
            .position(|name| name == column)
            .and_then(|index| self.values.get(index))
    }

    fn required(&self, column: &str) -> PyResult<Bound<'py, PyAny>> {
        self.get(column)
            .cloned()
            .ok_or_else(|| PyKeyError::new_err(column.to_owned()))
    }

    fn text(&self, column: &str) -> PyResult<Bound<'py, PyAny>> {
        Ok(self.required(column)?.str()?.into_any())
    }

    fn optional_text(&self, column: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
        match self.get(column) {
            Some(value) if !value.is_none() => Ok(Some(value.str()?.into_any())),
            _ => Ok(None),
        }
    }

    fn nullable(&self, py: Python<'py>, column: &str) -> PyResult<Bound<'py, PyAny>> {
        Ok(self
            .optional_text(column)?
            .unwrap_or_else(|| py.None().into_bound(py)))
    }

    fn relation(&self, py: Python<'py>, prefix: &str) -> PyResult<Bound<'py, PyAny>> {
        call_with(
            &imported(py, MIGRATION_MODELS, "MigrationRelation")?,
            &[
                (
                    "database",
                    self.nullable(py, &format!("{prefix}_database"))?,
                ),
                ("schema", self.nullable(py, &format!("{prefix}_schema"))?),
                ("name", self.text(&format!("{prefix}_name"))?),
            ],
        )
    }
}

/// `decode_event_timestamp`: a stored timestamp as an aware datetime, naive values read as UTC.
fn timestamp<'py>(raw: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = raw.py();
    let parsed: Bound<'py, PyAny> = if date_time_typed(raw)? {
        raw.clone()
    } else {
        imported(py, DATETIME_MODULE, "datetime")?.call_method1("fromisoformat", (raw.str()?,))?
    };
    if !parsed.getattr("tzinfo")?.is_none() {
        return Ok(parsed);
    }
    let utc: Bound<'py, PyDict> = PyDict::new(py);
    utc.set_item("tzinfo", imported(py, DATETIME_MODULE, "UTC")?)?;
    parsed.call_method("replace", (), Some(&utc))
}

fn enumerated<'py>(
    py: Python<'py>,
    class: &str,
    value: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    imported(py, MIGRATION_TYPES, class)?.call1((value,))
}

fn known_member<'py>(
    py: Python<'py>,
    class: &str,
    value: Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    match enumerated(py, class, value) {
        Ok(member) => Ok(Some(member)),
        Err(error) if error.is_instance_of::<PyValueError>(py) => Ok(None),
        Err(error) => Err(error),
    }
}

fn model_event<'py>(py: Python<'py>, row: &StoredRow<'_, 'py>) -> PyResult<Bound<'py, PyAny>> {
    let created_at: Bound<'py, PyAny> = timestamp(&row.required("created_at")?)?;
    let version_hash: Bound<'py, PyAny> = row.required("origin_version_hash")?;
    let version_hash: Bound<'py, PyAny> = if version_hash.is_truthy()? {
        version_hash.str()?.into_any()
    } else {
        PyString::new(py, "").into_any()
    };
    call_with(
        &imported(py, MIGRATION_MODELS, "MigrationEvent")?,
        &[
            ("event_id", row.text("event_id")?),
            ("target_name", row.nullable(py, "target_name")?),
            ("origin_model", row.nullable(py, "origin_model")?),
            ("origin", row.relation(py, "origin")?),
            ("destination_model", row.text("destination_model")?),
            ("destination", row.relation(py, "destination")?),
            ("origin_version_hash", version_hash),
            (
                "discovery",
                enumerated(py, "MigrationDiscovery", row.text("discovery")?)?,
            ),
            (
                "decision",
                enumerated(py, "MigrationDecision", row.text("decision")?)?,
            ),
            ("run_id", row.text("run_id")?),
            ("created_at", created_at),
        ],
    )
}

fn column_event<'py>(py: Python<'py>, row: &StoredRow<'_, 'py>) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(py, MIGRATION_MODELS, "ColumnMigrationEvent")?,
        &[
            ("event_id", row.text("event_id")?),
            ("target_name", row.nullable(py, "target_name")?),
            ("model_name", row.text("model_name")?),
            ("relation", row.relation(py, "relation")?),
            ("origin_column", row.text("origin_column")?),
            ("destination_column", row.text("destination_column")?),
            (
                "discovery",
                enumerated(py, "MigrationDiscovery", row.text("discovery")?)?,
            ),
            (
                "decision",
                enumerated(py, "ColumnMigrationDecision", row.text("decision")?)?,
            ),
            ("run_id", row.text("run_id")?),
            ("created_at", timestamp(&row.required("created_at")?)?),
        ],
    )
}

fn stored_text(row: &StoredRow<'_, '_>, column: &str) -> PyResult<Option<String>> {
    row.optional_text(column)?
        .map(|value| value.extract())
        .transpose()
}

fn old_name_event<'py>(
    py: Python<'py>,
    row: &StoredRow<'_, 'py>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let raw_type: Bound<'py, PyAny> = match row.get("event_type") {
        Some(value) => value.str()?.into_any(),
        None => PyString::new(py, "None").into_any(),
    };
    let Some(event_type) = known_member(py, "OldNameViewEventType", raw_type)? else {
        return Ok(None);
    };
    let drop_reason: Option<Bound<'py, PyAny>> = match row.optional_text("drop_reason")? {
        Some(raw) => known_member(py, "OldNameViewDropReason", raw)?,
        None => None,
    };
    let none = || py.None().into_bound(py);
    let expires_at: Bound<'py, PyAny> = match row.get("expires_at") {
        Some(raw) if !raw.is_none() => timestamp(raw)?,
        _ => none(),
    };
    let aliases: Vec<(String, String)> =
        decoded_column_aliases(stored_text(row, "column_aliases")?.as_deref());
    let grants: Bound<'py, PyAny> =
        match decoded_grants(stored_text(row, "grants_copied")?.as_deref()) {
            Some(grants) => PyTuple::new(py, grants)?.into_any(),
            None => none(),
        };
    let fields: [(&str, Bound<'py, PyAny>); 16] = [
        ("event_id", row.text("event_id")?),
        ("target_name", row.nullable(py, "target_name")?),
        ("event_type", event_type),
        ("migration_event_id", row.text("migration_event_id")?),
        ("destination_model", row.text("destination_model")?),
        ("old", row.relation(py, "old")?),
        ("new", row.relation(py, "new")?),
        ("run_id", row.text("run_id")?),
        ("created_at", timestamp(&row.required("created_at")?)?),
        ("view_retention", row.nullable(py, "view_retention")?),
        ("archive_name", row.nullable(py, "archive_name")?),
        ("column_aliases", PyTuple::new(py, aliases)?.into_any()),
        ("expires_at", expires_at),
        ("drop_reason", drop_reason.unwrap_or_else(none)),
        ("grants_copied", grants),
        ("view_sql", row.nullable(py, "view_sql")?),
    ];
    call_with(
        &imported(py, MIGRATION_MODELS, "OldNameViewEvent")?,
        &fields,
    )
    .map(Some)
}

/// Stored rows of the selected `columns` as events; rows this version cannot read are skipped.
#[pyfunction(name = "decode_migration_event_rows")]
#[pyo3(signature = (*, kind, rows, columns))]
fn decode_rows<'py>(
    kind: &str,
    rows: &Bound<'py, PyAny>,
    columns: Vec<String>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = rows.py();
    let table: EventTable = layout(kind)?.table;
    let mut events: Vec<Bound<'py, PyAny>> = Vec::new();
    for row in rows.try_iter()? {
        let values: Vec<Bound<'py, PyAny>> = row?.try_iter()?.collect::<PyResult<_>>()?;
        let stored = StoredRow {
            columns: &columns,
            values,
        };
        let decoded: Option<Bound<'py, PyAny>> = match table {
            EventTable::Model => Some(model_event(py, &stored)?),
            EventTable::Column => match column_event(py, &stored) {
                Ok(event) => Some(event),
                Err(error) if error.is_instance_of::<PyValueError>(py) => None,
                Err(error) => return Err(error),
            },
            EventTable::OldName => old_name_event(py, &stored)?,
        };
        events.extend(decoded);
    }
    PyTuple::new(py, events)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(create_sql, module)?)?;
    module.add_function(wrap_pyfunction!(read_sql, module)?)?;
    module.add_function(wrap_pyfunction!(write_sql, module)?)?;
    module.add_function(wrap_pyfunction!(decode_rows, module)?)?;
    Ok(())
}
