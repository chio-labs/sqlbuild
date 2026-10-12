//! What each model, seed, source and table function declares about its columns before analysis.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};

const UNKNOWN_TYPE: &str = "UNKNOWN";
const NOT_NULL_AUDIT_NAME: &str = "not_null";
const ENFORCED_CONTRACT: &str = "enforced";
const CONTRACT_KEY: &str = "contract";
const TABLE_FUNCTION_PREFIX: &str = "__sqlbuild_table_function_";
const NULLABILITY_MODULE: &str = "sqlbuild.compiler.lineage.types";
const NULLABILITY_CLASS: &str = "InferredNullability";
const NON_NULL_MEMBER: &str = "NON_NULL";
const UNKNOWN_MEMBER: &str = "UNKNOWN";

/// The three per-relation declaration maps the analysis starts from.
type DeclaredRelations<'py> = (Bound<'py, PyDict>, Bound<'py, PyDict>, Bound<'py, PyDict>);

/// `{column.name: column.type or "UNKNOWN"}`, or the declared type unchanged when `exact`.
fn column_types<'py>(columns: &Bound<'py, PyAny>, exact: bool) -> PyResult<Bound<'py, PyDict>> {
    let types: Bound<'py, PyDict> = PyDict::new(columns.py());
    for column in columns.try_iter()? {
        let column: Bound<'py, PyAny> = column?;
        let declared: Bound<'py, PyAny> = column.getattr("type")?;
        if exact || declared.is_truthy()? {
            types.set_item(column.getattr("name")?, declared)?;
        } else {
            types.set_item(column.getattr("name")?, UNKNOWN_TYPE)?;
        }
    }
    Ok(types)
}

/// Each column's declared nullability: non-null when `nullable` is false or a `not_null` audit.
fn column_nullability<'py>(
    columns: &Bound<'py, PyAny>,
    nullability: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let facts: Bound<'py, PyDict> = PyDict::new(columns.py());
    for column in columns.try_iter()? {
        let column: Bound<'py, PyAny> = column?;
        let mut non_null: bool = column
            .getattr("nullable")?
            .is(PyBool::new(columns.py(), false).as_any());
        for audit in column.getattr("audits")?.try_iter()? {
            non_null = non_null || audit?.getattr("definition_name")?.eq(NOT_NULL_AUDIT_NAME)?;
        }
        let state: &str = if non_null {
            NON_NULL_MEMBER
        } else {
            UNKNOWN_MEMBER
        };
        facts.set_item(column.getattr("name")?, nullability.getattr(state)?)?;
    }
    Ok(facts)
}

fn table_function_name(function: &Bound<'_, PyAny>) -> PyResult<String> {
    let name: String = function.getattr("name")?.extract()?;
    Ok(format!("{TABLE_FUNCTION_PREFIX}{name}"))
}

/// Declared column types, declared nullability and the authoritative binding schemas.
#[pyfunction]
fn declared_relations<'py>(inputs: Bound<'py, PyAny>) -> PyResult<DeclaredRelations<'py>> {
    let py: Python<'py> = inputs.py();
    let nullability: Bound<'py, PyAny> =
        py.import(NULLABILITY_MODULE)?.getattr(NULLABILITY_CLASS)?;
    let types: Bound<'py, PyDict> = PyDict::new(py);
    let nulls: Bound<'py, PyDict> = PyDict::new(py);
    let complete: Bound<'py, PyDict> = PyDict::new(py);
    for model in inputs.getattr("model_inputs")?.try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        let entry: Bound<'py, PyAny> = model.getattr("schema_entry")?;
        if entry.is_none() {
            continue;
        }
        let name: Bound<'py, PyAny> = entry.getattr("name")?;
        let columns: Bound<'py, PyAny> = entry.getattr("columns")?;
        types.set_item(&name, column_types(&columns, false)?)?;
        nulls.set_item(&name, column_nullability(&columns, &nullability)?)?;
        let contract: Option<Bound<'py, PyAny>> = model
            .getattr("config")?
            .getattr("values")?
            .downcast_into::<PyDict>()?
            .get_item(CONTRACT_KEY)?;
        let enforced: bool = match contract {
            Some(contract) => contract.eq(ENFORCED_CONTRACT)?,
            None => false,
        };
        if enforced && columns.is_truthy()? && !entry.getattr("dynamic_columns")?.is_truthy()? {
            let stem: Bound<'py, PyAny> = model
                .getattr("model_file")?
                .getattr("file_path")?
                .getattr("stem")?;
            complete.set_item(stem, column_types(&columns, false)?)?;
        }
    }
    let mut seeds: Vec<(Bound<'py, PyAny>, Bound<'py, PyAny>)> = Vec::new();
    for seed in inputs.getattr("seed_inputs")?.try_iter()? {
        let entry: Bound<'py, PyAny> = seed?.getattr("schema_entry")?;
        let name: Bound<'py, PyAny> = entry.getattr("name")?;
        let columns: Bound<'py, PyAny> = entry.getattr("columns")?;
        types.set_item(&name, column_types(&columns, false)?)?;
        nulls.set_item(&name, column_nullability(&columns, &nullability)?)?;
        seeds.push((name, columns));
    }
    for source in inputs.getattr("source_inputs")?.try_iter()? {
        let entry: Bound<'py, PyAny> = source?.getattr("source_entry")?;
        let name: Bound<'py, PyAny> = entry.getattr("name")?;
        let columns: Bound<'py, PyAny> = entry.getattr("columns")?;
        types.set_item(&name, column_types(&columns, false)?)?;
        nulls.set_item(&name, column_nullability(&columns, &nullability)?)?;
        if entry.getattr(CONTRACT_KEY)?.eq(ENFORCED_CONTRACT)? && columns.is_truthy()? {
            complete.set_item(&name, column_types(&columns, false)?)?;
        }
    }
    for (name, columns) in seeds {
        if columns.is_truthy()? {
            complete.set_item(name, column_types(&columns, false)?)?;
        }
    }
    for function in inputs.getattr("sql_function_inputs")?.try_iter()? {
        let function: Bound<'py, PyAny> = function?;
        let columns: Bound<'py, PyAny> = function.getattr("return_columns")?;
        if !columns.is_truthy()? {
            continue;
        }
        let name: String = table_function_name(&function)?;
        types.set_item(&name, column_types(&columns, true)?)?;
        let unknown: Bound<'py, PyDict> = PyDict::new(py);
        for column in columns.try_iter()? {
            unknown.set_item(
                column?.getattr("name")?,
                nullability.getattr(UNKNOWN_MEMBER)?,
            )?;
        }
        nulls.set_item(&name, unknown)?;
        complete.set_item(&name, column_types(&columns, true)?)?;
    }
    Ok((types, nulls, complete))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(declared_relations, module)?)
}
