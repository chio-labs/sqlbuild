//! Source contract validation and adapter-controlled projection rendering.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_resolution::values::{cursor_wrap, method, string};
use crate::bindings::_helpers::planner_strategy::values::{PLANNER_EXCEPTIONS_MODULE, input_error};
use crate::bindings::_helpers::references::source_relations::render_source_relation;
use pyo3::IntoPyObject;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_sqltext::resolution::main::{
    reference_spans::reference_spans, source_alias::source_alias,
};

const TYPES_MODULE: &str = "sqlbuild.adapter.type_system.main.types_equal";

fn source_error(py: Python<'_>, message: &str, code: &str) -> PyErr {
    input_error(
        py,
        (PLANNER_EXCEPTIONS_MODULE, "PlannerInputError"),
        message,
        Some(code),
    )
}

fn rows(value: &Bound<'_, PyAny>) -> PyResult<Vec<(String, Option<String>)>> {
    value
        .try_iter()?
        .map(|row| {
            let row = row?;
            Ok((
                row.getattr("name")?.extract()?,
                row.getattr("type")?.extract()?,
            ))
        })
        .collect()
}

fn check_columns(
    entry: &Bound<'_, PyAny>,
    columns: &Bound<'_, PyAny>,
    adapter: &Bound<'_, PyAny>,
    relation: &str,
) -> PyResult<()> {
    let py = entry.py();
    let declared = rows(&entry.getattr("columns")?)?;
    let available = rows(columns)?;
    let available: std::collections::HashMap<String, Option<String>> = available
        .into_iter()
        .map(|(name, kind)| (name.to_lowercase(), kind))
        .collect();
    let missing = declared
        .iter()
        .filter(|(name, _)| !available.contains_key(&name.to_lowercase()))
        .map(|(name, _)| name.as_str())
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        return Err(source_error(
            py,
            &format!(
                "source {relation} declares columns not found in warehouse: {}",
                missing.join(", ")
            ),
            "S401",
        ));
    }
    if entry
        .getattr("contract")?
        .extract::<Option<String>>()?
        .as_deref()
        != Some("enforced")
    {
        return Ok(());
    }
    for (name, kind) in declared {
        let Some(kind) = kind else {
            continue;
        };
        let Some(Some(actual)) = available.get(&name.to_lowercase()) else {
            continue;
        };
        if actual.is_empty() {
            continue;
        }
        let equal = call_with(
            &imported(py, TYPES_MODULE, "types_equal")?,
            &[
                ("left", string(py, actual)),
                ("right", string(py, &kind)),
                ("dialect", adapter.getattr("sql_analysis_dialect_name")?),
            ],
        )?
        .is_truthy()?;
        if !equal {
            return Err(source_error(
                py,
                &format!(
                    "source {relation} column '{name}' has type {actual} but contract declares {kind}"
                ),
                "S404",
            ));
        }
    }
    Ok(())
}

fn cast_projection<'py>(
    adapter: &Bound<'py, PyAny>,
    name: &str,
    declared: &str,
    kind: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let py = adapter.py();
    method(
        adapter,
        "render_source_expression_cast",
        &[
            (
                "expression",
                adapter.call_method1("render_identifier", (name,))?,
            ),
            ("target_type", string(py, kind)),
            (
                "alias",
                adapter.call_method1("render_identifier", (declared,))?,
            ),
        ],
    )
}

fn cast_source(
    entry: &Bound<'_, PyAny>,
    columns: &Bound<'_, PyAny>,
    adapter: &Bound<'_, PyAny>,
    relation: String,
) -> PyResult<String> {
    let declared = rows(&entry.getattr("columns")?)?;
    if !declared.iter().any(|(_, kind)| kind.is_some()) {
        return Ok(relation);
    }
    let py = entry.py();
    let expression = !entry.getattr("expression")?.is_none();
    let source_name: String = entry.getattr("name")?.extract()?;
    if columns.is_none() {
        if expression {
            return Err(source_error(
                py,
                &format!(
                    "source expression '{source_name}' type enforcement requires query output column metadata"
                ),
                "S402",
            ));
        }
        return Ok(relation);
    }
    let available = rows(columns)?;
    let plan = sqlbuild_sqltext::resolution::main::source_cast_plan::source_cast_plan(
        &declared, &available, expression,
    );
    let names: Vec<&str> = available.iter().map(|(name, _)| name.as_str()).collect();
    if expression {
        let name_map: std::collections::HashMap<String, &str> = names
            .iter()
            .map(|name| (name.to_lowercase(), *name))
            .collect();
        let missing = declared
            .iter()
            .filter(|(name, _)| !name_map.contains_key(&name.to_lowercase()))
            .map(|(name, _)| name.as_str())
            .collect::<Vec<_>>();
        if !missing.is_empty() {
            let available = if names.is_empty() {
                "<none>".to_owned()
            } else {
                names.join(", ")
            };
            return Err(source_error(
                py,
                &format!(
                    "source expression '{source_name}' declares columns not found in query output: {}. Available query output columns: {available}",
                    missing.join(", ")
                ),
                "S403",
            ));
        }
        let mut projections: Vec<Bound<'_, PyAny>> = Vec::new();
        for projection in &plan.projections {
            projections.push(if let Some((declared, kind)) = &projection.cast {
                cast_projection(adapter, &projection.name, declared, kind)?
            } else {
                adapter.call_method1("render_identifier", (&projection.name,))?
            });
        }
        return method(
            adapter,
            "render_source_expression_cast_subquery",
            &[
                ("source_relation", string(py, &relation)),
                ("projections", PyTuple::new(py, projections)?.into_any()),
            ],
        )?
        .extract();
    }
    if plan.projections.is_empty() {
        return Ok(relation);
    }
    let mut projections: Vec<Bound<'_, PyAny>> = Vec::new();
    for projection in &plan.projections {
        if let Some((name, kind)) = &projection.cast {
            projections.push(cast_projection(adapter, &projection.name, name, kind)?);
        }
    }
    method(
        adapter,
        "_render_source_relation_cast_subquery_with_columns",
        &[
            ("source_relation", string(py, &relation)),
            (
                "cast_projections",
                PyTuple::new(py, projections)?.into_any(),
            ),
            (
                "cast_column_names",
                PyTuple::new(
                    py,
                    plan.projections.iter().map(|projection| &projection.name),
                )?
                .into_any(),
            ),
            (
                "warehouse_column_names",
                PyTuple::new(py, names)?.into_any(),
            ),
            (
                "all_columns_cast",
                plan.all_columns_cast
                    .into_pyobject(py)?
                    .to_owned()
                    .into_any(),
            ),
        ],
    )?
    .extract()
}

#[pyfunction]
#[pyo3(signature = (*, adapter, source_entry))]
fn render_source_read_relation(
    adapter: &Bound<'_, PyAny>,
    source_entry: &Bound<'_, PyAny>,
) -> PyResult<String> {
    render_source_relation(source_entry, Some(adapter))
}

fn resolve_one(args: &KeywordArguments<'_>, name: &str, original: &str) -> PyResult<String> {
    let entry = args.value("source_map")?.call_method1("get", (name,))?;
    if entry.is_none() {
        return Ok(original.to_owned());
    }
    let adapter = args.value("adapter")?;
    let mut relation = render_source_read_relation(&adapter, &entry)?;
    let columns = args
        .value("source_warehouse_columns")?
        .call_method1("get", (name,))?;
    let expression = !entry.getattr("expression")?.is_none();
    if columns.is_truthy()?
        && (!expression
            || entry
                .getattr("contract")?
                .extract::<Option<String>>()?
                .as_deref()
                == Some("enforced"))
    {
        let label = if expression {
            format!("source expression '{name}'")
        } else {
            relation.clone()
        };
        check_columns(&entry, &columns, &adapter, &label)?;
    }
    if entry.getattr("type_enforcement")?.is_truthy()? {
        relation = cast_source(&entry, &columns, &adapter, relation)?;
    }
    cursor_wrap(args, relation, name, false)
}

#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn resolve_source_references(
    py: Python<'_>,
    kwargs: Option<Bound<'_, PyDict>>,
) -> PyResult<String> {
    let args = KeywordArguments::read(
        py,
        "resolve_source_references",
        kwargs,
        (
            &[
                "query_sql",
                "source_map",
                "source_warehouse_columns",
                "star_exclude_keyword",
                "cursor_bounds",
                "cursor_filter_inputs",
                "adapter",
                "cursor_type",
                "lower_bound_inclusive",
            ],
            &[],
        ),
    )?;
    let sql: String = args.value("query_sql")?.extract()?;
    let aliases = args
        .value("adapter")?
        .call_method0("requires_derived_table_aliases")?
        .is_truthy()?;
    let mut output = String::new();
    let mut last = 0;
    for span in reference_spans(&sql, "source") {
        let mut relation = resolve_one(&args, &span.name, &sql[span.start..span.end])?;
        output.push_str(sql.get(last..span.start).unwrap_or_default());
        last = span.end;
        if aliases && relation.trim_start().starts_with('(') {
            let (end, alias) = source_alias(&sql, span.end, &span.name);
            relation.push_str(&format!(" AS {alias}"));
            last = end;
        }
        output.push_str(&relation);
    }
    output.push_str(&sql[last..]);
    Ok(output)
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_source_references, module)?)?;
    module.add_function(wrap_pyfunction!(render_source_read_relation, module)?)?;
    Ok(())
}
