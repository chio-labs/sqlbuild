//! A declared source rendered as the SQL table factor that reads it.

use crate::bindings::_helpers::records::fields::field as native_field;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};

/// Leading words of a source expression that is a query rather than a relation.
const QUERY_PREFIXES: [&str; 3] = ["select", "with", "values"];

/// A source expression as a table factor: queries parenthesized, relations as written.
fn expression_relation(expression: &str) -> String {
    let trimmed: &str = expression.trim();
    let stripped: &str = trimmed.strip_suffix(';').unwrap_or(trimmed).trim();
    if stripped.starts_with('(') {
        return stripped.to_owned();
    }
    let lowered: String = stripped.to_lowercase();
    if QUERY_PREFIXES
        .iter()
        .any(|prefix| lowered.starts_with(prefix))
    {
        return format!("({stripped})");
    }
    stripped.to_owned()
}

/// Render a source as a SQL table factor, through the adapter when one is given.
#[pyfunction]
#[pyo3(signature = (*, entry, adapter = None))]
pub(crate) fn render_source_relation<'py>(
    entry: &Bound<'py, PyAny>,
    adapter: Option<&Bound<'py, PyAny>>,
) -> PyResult<String> {
    let adapter: Option<&Bound<'py, PyAny>> = adapter.filter(|adapter| !adapter.is_none());
    let expression: Option<String> = native_field(entry, "expression")?.extract()?;
    if let Some(expression) = expression {
        return match adapter {
            Some(adapter) => {
                let keywords: Bound<'py, PyDict> = PyDict::new(entry.py());
                keywords.set_item("expression", expression)?;
                adapter
                    .call_method("render_source_expression_relation", (), Some(&keywords))?
                    .extract()
            }
            None => Ok(expression_relation(&expression)),
        };
    }
    let table: Option<String> = native_field(entry, "table")?.extract()?;
    let table: String = match table {
        Some(table) => table,
        None => native_field(entry, "name")?.extract()?,
    };
    let database: Option<String> = native_field(entry, "database")?.extract()?;
    let schema: Option<String> = native_field(entry, "schema")?.extract()?;
    if let Some(adapter) = adapter {
        let keywords: Bound<'py, PyDict> = PyDict::new(entry.py());
        keywords.set_item("database", &database)?;
        keywords.set_item("schema", &schema)?;
        keywords.set_item("name", &table)?;
        let rendered: Option<String> = adapter
            .call_method("render_qualified_name", (), Some(&keywords))?
            .extract()?;
        if let Some(rendered) = rendered {
            return Ok(rendered);
        }
    }
    Ok([database, schema, Some(table)]
        .into_iter()
        .flatten()
        .collect::<Vec<String>>()
        .join("."))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(render_source_relation, module)?)?;
    Ok(())
}
