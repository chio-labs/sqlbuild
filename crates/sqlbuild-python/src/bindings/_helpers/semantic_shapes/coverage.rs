//! Per-model reasons a semantic check was only partial, for machine reports.

use std::collections::{BTreeSet, HashMap, HashSet};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::analysis::model_reads::{inferred_rows, star_flags};
use crate::bindings::_helpers::compiled_project::compiled_model_view::InferredRow;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::semantic_shapes::shapes::project_shapes;

const TYPE_CHECKED_DIALECTS: [&str; 4] = ["duckdb", "snowflake", "postgresql", "bigquery"];
const SOURCE_KIND: &str = "source";
const OPEN_KINDS: [&str; 3] = [SOURCE_KIND, "ref", "dbt_ref"];

/// Partial-check reasons by model name; empty when SQL analysis is off.
#[pyfunction]
pub(crate) fn semantic_coverage<'py>(project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = project.py();
    let reasons: Bound<'py, PyDict> = PyDict::new(py);
    if !native_field(&native_field(project, "settings")?, "sql_analysis")?.is_truthy()? {
        return Ok(reasons);
    }
    let shapes: Bound<'py, PyDict> = project_shapes(project, None)?;
    let models: Vec<Bound<'py, PyAny>> = native_field(project, "models")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let mut names: Vec<String> = Vec::with_capacity(models.len());
    let mut references: Vec<Vec<(String, String)>> = Vec::with_capacity(models.len());
    let mut blocked_by: HashMap<String, HashSet<String>> = HashMap::new();
    for model in &models {
        let name: String = native_field(model, "name")?.extract()?;
        let mut rows: Vec<(String, String)> = Vec::new();
        for row in native_field(model, "reference_rows")?.try_iter()? {
            let row: Bound<'py, PyAny> = row?;
            rows.push((
                row.get_item(0)?.str()?.extract()?,
                row.get_item(1)?.extract()?,
            ));
        }
        for item in native_field(model, "binding_diagnostics")?.try_iter()? {
            if native_field(&item?, "is_error")?.is_truthy()? {
                blocked_by.insert(name.clone(), HashSet::from([name.clone()]));
                break;
            }
        }
        names.push(name);
        references.push(rows);
    }
    if !blocked_by.is_empty() {
        for _ in &names {
            let mut changed: bool = false;
            for (name, rows) in names.iter().zip(&references) {
                let mut causes: HashSet<String> = blocked_by.get(name).cloned().unwrap_or_default();
                for (_, upstream) in rows {
                    causes.extend(blocked_by.get(upstream).cloned().unwrap_or_default());
                }
                if !causes.is_empty() && blocked_by.get(name) != Some(&causes) {
                    blocked_by.insert(name.clone(), causes);
                    changed = true;
                }
            }
            if !changed {
                break;
            }
        }
    }
    let dialect: Bound<'py, PyAny> = native_field(project, "sql_analysis_dialect")?;
    let dialect: String = if dialect.is_truthy()? {
        dialect.extract()?
    } else {
        "generic".to_owned()
    };
    for ((model, name), rows) in models.iter().zip(&names).zip(&references) {
        let opted: Bound<'py, PyAny> = native_field(&native_field(model, "config")?, "values")?
            .call_method1("get", ("sql_analysis",))?;
        if opted.is(PyBool::new(py, false)) {
            reasons.set_item(name, PyTuple::new(py, ["SQL analysis disabled"])?)?;
            continue;
        }
        let mut partial: BTreeSet<String> = BTreeSet::new();
        for (kind, upstream) in rows {
            if OPEN_KINDS.contains(&kind.as_str()) && !shapes.contains(upstream)? {
                partial.insert(if kind == SOURCE_KIND {
                    format!("open source: {upstream}")
                } else {
                    format!("open input: {upstream}")
                });
            }
        }
        if let Some(causes) = blocked_by.get(name) {
            for cause in causes.iter().filter(|cause| *cause != name) {
                partial.insert(format!("depends on invalid model {cause}"));
            }
        }
        let inferred: Vec<InferredRow> = inferred_rows(model)?.unwrap_or_default();
        if inferred.is_empty() {
            partial.insert("output shape could not be inferred".to_owned());
        } else if star_flags(model)?.0 && !shapes.contains(name)? {
            partial.insert("unresolved star over open inputs".to_owned());
        }
        if inferred
            .iter()
            .any(|(_, column_type, _)| column_type.is_none())
        {
            partial.insert("some output types are unknown".to_owned());
        }
        if !TYPE_CHECKED_DIALECTS.contains(&dialect.as_str()) {
            partial.insert("type checking awaits dialect coercion support".to_owned());
        }
        if !partial.is_empty() {
            reasons.set_item(name, PyTuple::new(py, partial)?)?;
        }
    }
    Ok(reasons)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(semantic_coverage, module)?)
}
