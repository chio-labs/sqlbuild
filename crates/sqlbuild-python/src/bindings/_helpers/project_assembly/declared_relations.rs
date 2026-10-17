//! What each model, seed, source and table function declares about its columns before analysis.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use sqlbuild_analysis::compiled_project::models::SchemaColumnFact;

use crate::bindings::_helpers::compiled_project::model_input_view::{
    attached_columns, attached_schema,
};
use crate::bindings::_helpers::compiled_project::schema_facts::python_column_facts;
use crate::bindings::_helpers::records::construct::{enum_member, record_class};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::RecordId;

const UNKNOWN_TYPE: &str = "UNKNOWN";
const NOT_NULL_AUDIT_NAME: &str = "not_null";
const ENFORCED_CONTRACT: &str = "enforced";
const CONTRACT_KEY: &str = "contract";
const TABLE_FUNCTION_PREFIX: &str = "__sqlbuild_table_function_";
const NON_NULL_MEMBER: &str = "NON_NULL";
const UNKNOWN_MEMBER: &str = "UNKNOWN";

/// The three per-relation declaration maps the analysis starts from.
pub(crate) type DeclaredRelations<'py> =
    (Bound<'py, PyDict>, Bound<'py, PyDict>, Bound<'py, PyDict>);

/// `{column.name: column.type or "UNKNOWN"}`, or the declared type unchanged when `exact`.
fn column_types<'py>(
    py: Python<'py>,
    columns: &[SchemaColumnFact],
    exact: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let types: Bound<'py, PyDict> = PyDict::new(py);
    for column in columns {
        match column.data_type.as_deref() {
            Some(declared) if exact || !declared.is_empty() => {
                types.set_item(&column.name, declared)?;
            }
            None if exact => types.set_item(&column.name, py.None())?,
            _ => types.set_item(&column.name, UNKNOWN_TYPE)?,
        }
    }
    Ok(types)
}

/// Each column's declared nullability: non-null when `nullable` is false or a `not_null` audit.
fn column_nullability<'py>(
    columns: &[SchemaColumnFact],
    nullability: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let facts: Bound<'py, PyDict> = PyDict::new(nullability.py());
    let non_null_member: Bound<'py, PyAny> = nullability.getattr(NON_NULL_MEMBER)?;
    let unknown_member: Bound<'py, PyAny> = nullability.getattr(UNKNOWN_MEMBER)?;
    for column in columns {
        let non_null: bool = column.nullable == Some(false)
            || column
                .audit_definitions
                .iter()
                .any(|definition| definition == NOT_NULL_AUDIT_NAME);
        let state: &Bound<'py, PyAny> = if non_null {
            &non_null_member
        } else {
            &unknown_member
        };
        facts.set_item(&column.name, state)?;
    }
    Ok(facts)
}

fn table_function_name(function: &Bound<'_, PyAny>) -> PyResult<String> {
    let name: String = native_field(function, "name")?.extract()?;
    Ok(format!("{TABLE_FUNCTION_PREFIX}{name}"))
}

/// Declared column types, declared nullability and the authoritative binding schemas.
pub(crate) fn declared_relations<'py>(
    inputs: Bound<'py, PyAny>,
) -> PyResult<DeclaredRelations<'py>> {
    let py: Python<'py> = inputs.py();
    let nullability: Bound<'py, PyAny> = record_class(py, RecordId::InferredNullability)?;
    let types: Bound<'py, PyDict> = PyDict::new(py);
    let nulls: Bound<'py, PyDict> = PyDict::new(py);
    let complete: Bound<'py, PyDict> = PyDict::new(py);
    for model in native_field(&inputs, "model_inputs")?.try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        let Some(schema) = attached_schema(&model)? else {
            continue;
        };
        let (name, columns): (String, Vec<SchemaColumnFact>) =
            (schema.name, attached_columns(&model)?);
        types.set_item(&name, column_types(py, &columns, false)?)?;
        nulls.set_item(&name, column_nullability(&columns, &nullability)?)?;
        let contract: Option<Bound<'py, PyAny>> =
            native_field(&native_field(&model, "config")?, "values")?
                .downcast_into::<PyDict>()?
                .get_item(CONTRACT_KEY)?;
        let enforced: bool = match contract {
            Some(contract) => contract.eq(ENFORCED_CONTRACT)?,
            None => false,
        };
        if enforced && !columns.is_empty() && !schema.dynamic_columns.is_truthy()? {
            complete.set_item(&name, column_types(py, &columns, false)?)?;
        }
    }
    let mut seeds: Vec<(Bound<'py, PyAny>, Vec<SchemaColumnFact>)> = Vec::new();
    for seed in native_field(&inputs, "seed_inputs")?.try_iter()? {
        let entry: Bound<'py, PyAny> = native_field(&seed?, "schema_entry")?;
        let name: Bound<'py, PyAny> = native_field(&entry, "name")?;
        let columns: Vec<SchemaColumnFact> =
            python_column_facts(&native_field(&entry, "columns")?, None)?;
        types.set_item(&name, column_types(py, &columns, false)?)?;
        nulls.set_item(&name, column_nullability(&columns, &nullability)?)?;
        seeds.push((name, columns));
    }
    for source in native_field(&inputs, "source_inputs")?.try_iter()? {
        let entry: Bound<'py, PyAny> = native_field(&source?, "source_entry")?;
        let name: Bound<'py, PyAny> = native_field(&entry, "name")?;
        let columns: Vec<SchemaColumnFact> =
            python_column_facts(&native_field(&entry, "columns")?, None)?;
        types.set_item(&name, column_types(py, &columns, false)?)?;
        nulls.set_item(&name, column_nullability(&columns, &nullability)?)?;
        if entry.getattr(CONTRACT_KEY)?.eq(ENFORCED_CONTRACT)? && !columns.is_empty() {
            complete.set_item(&name, column_types(py, &columns, false)?)?;
        }
    }
    for (name, columns) in seeds {
        if !columns.is_empty() {
            complete.set_item(name, column_types(py, &columns, false)?)?;
        }
    }
    for function in native_field(&inputs, "sql_function_inputs")?.try_iter()? {
        let function: Bound<'py, PyAny> = function?;
        let columns: Vec<SchemaColumnFact> =
            python_column_facts(&native_field(&function, "return_columns")?, None)?;
        if columns.is_empty() {
            continue;
        }
        let name: String = table_function_name(&function)?;
        types.set_item(&name, column_types(py, &columns, true)?)?;
        let unknown: Bound<'py, PyDict> = PyDict::new(py);
        for column in &columns {
            unknown.set_item(
                &column.name,
                enum_member(py, RecordId::InferredNullability, UNKNOWN_MEMBER)?,
            )?;
        }
        nulls.set_item(&name, unknown)?;
        complete.set_item(&name, column_types(py, &columns, true)?)?;
    }
    Ok((types, nulls, complete))
}
