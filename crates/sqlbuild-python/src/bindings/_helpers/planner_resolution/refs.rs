//! Reference lookup and adapter callbacks for planner SQL.

use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::native_host::adapter::AdapterHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::planner_resolution::values::{cursor_wrap, method, string};
use crate::bindings::_helpers::records::ids::NativeAttr;
use crate::bindings::_helpers::records::registry;
use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_sqltext::resolution::main::{ref_alias::ref_alias, reference_spans::reference_spans};

#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn resolve_ref_references(py: Python<'_>, kwargs: Option<Bound<'_, PyDict>>) -> PyResult<String> {
    let args = KeywordArguments::read(
        py,
        "resolve_ref_references",
        kwargs,
        (
            &[
                "query_sql",
                "model_locations",
                "seed_locations",
                "cursor_bounds",
                "cursor_filter_inputs",
                "adapter",
                "cursor_type",
                "lower_bound_inclusive",
            ],
            &[],
        ),
    )?;
    let original: String = args.value("query_sql")?.extract()?;
    let mut sql = original.clone();
    for (kind, key) in [("ref", "model_locations"), ("seed", "seed_locations")] {
        let locations = args.value(key)?;
        let mut output = String::new();
        let mut last = 0;
        for span in reference_spans(&sql, kind) {
            output.push_str(&sql[last..span.start]);
            let target = locations.call_method1("get", (&span.name,))?;
            if target.is_none() {
                output.push_str(&sql[span.start..span.end]);
            } else {
                let relation: String = call_with(
                    &host::entry(py, AdapterHost::ResolveRelationLocationQualifiedName)?,
                    &[("adapter", args.value("adapter")?), ("location", target)],
                )?
                .extract()?;
                let char_end = sql[..span.end].chars().count();
                let original_end = original
                    .char_indices()
                    .nth(char_end)
                    .map_or(original.len(), |(offset, _)| offset);
                output.push_str(&cursor_wrap(
                    &args,
                    relation,
                    &span.name,
                    !ref_alias(&original, original_end),
                )?);
            }
            last = span.end;
        }
        output.push_str(&sql[last..]);
        sql = output;
    }
    Ok(sql)
}

#[pyfunction]
#[pyo3(signature = (*, query_sql, external_sql_reference_resolver=None))]
fn resolve_dbt_ref_references(
    query_sql: &str,
    external_sql_reference_resolver: Option<&Bound<'_, PyAny>>,
) -> PyResult<String> {
    let Some(resolver) = external_sql_reference_resolver.filter(|value| !value.is_none()) else {
        return Ok(query_sql.to_owned());
    };
    let py = resolver.py();
    let mut output = String::new();
    let mut last = 0;
    for span in reference_spans(query_sql, "dbt_ref") {
        output.push_str(&query_sql[last..span.start]);
        let relation: Option<String> = method(
            resolver,
            "resolve_reference",
            &[
                ("ref_kind", string(py, "dbt_ref")),
                ("ref_package", span.package.into_pyobject(py)?.into_any()),
                ("ref_name", string(py, &span.name)),
            ],
        )?
        .extract()?;
        output.push_str(
            relation
                .as_deref()
                .unwrap_or(&query_sql[span.start..span.end]),
        );
        last = span.end;
    }
    output.push_str(&query_sql[last..]);
    Ok(output)
}

fn resolve_function_calls(
    query_sql: &str,
    locations: &Bound<'_, PyAny>,
    adapter: &Bound<'_, PyAny>,
    table: bool,
) -> PyResult<String> {
    let py = adapter.py();
    let kind = if table { "table_fn" } else { "udf" };
    let spans = reference_spans(query_sql, kind);
    if spans.is_empty() {
        return Ok(query_sql.to_owned());
    }
    let scanner_type = registry::native(py, NativeAttr::SqlCodeScanner)?;
    let scan = scanner_type.call1((query_sql, py.None(), "SQL reference resolution"))?;
    let mut output = String::new();
    let mut last = 0;
    let mut code_index = 0;
    for span in spans {
        if table {
            let start = query_sql[..span.start].chars().count();
            while code_index < start {
                let end: Option<usize> = scan
                    .call_method1("non_code_end", (code_index,))?
                    .extract()?;
                code_index = end.unwrap_or(code_index + 1);
            }
            if code_index > start {
                continue;
            }
            code_index = query_sql[..span.end].chars().count();
        }
        output.push_str(query_sql.get(last..span.start).unwrap_or_default());
        let target = locations.call_method1("get", (&span.name,))?;
        let qualified = if target.is_none() {
            py.None().into_bound(py)
        } else {
            target.getattr("qualified_name")?
        };
        let suffix =
            span.end + query_sql[span.end..].len() - query_sql[span.end..].trim_start().len();
        if qualified.is_none() || !query_sql[suffix..].starts_with('(') {
            output.push_str(&query_sql[span.start..span.end]);
            last = span.end;
            continue;
        }
        let context = if table {
            "SQL table function call"
        } else {
            "SQL UDF call"
        };
        let scanner = scanner_type.call1((query_sql, py.None(), context))?;
        let end: usize = scanner
            .call_method1("matching_paren", (query_sql[..suffix].chars().count(),))?
            .extract()?;
        let end = query_sql
            .char_indices()
            .nth(end + 1)
            .map_or(query_sql.len(), |(index, _)| index);
        let hook = if table {
            "render_table_function_call"
        } else {
            "render_udf_call"
        };
        let rendered: String = method(
            adapter,
            hook,
            &[
                ("target", qualified),
                ("call_suffix_sql", string(py, &query_sql[suffix..end])),
            ],
        )?
        .extract()?;
        output.push_str(&rendered);
        last = end;
    }
    if table {
        let length = query_sql.chars().count();
        while code_index < length {
            let end: Option<usize> = scan
                .call_method1("non_code_end", (code_index,))?
                .extract()?;
            code_index = end.unwrap_or(code_index + 1);
        }
    }
    output.push_str(&query_sql[last..]);
    Ok(output)
}

#[pyfunction]
#[pyo3(signature = (*, query_sql, function_locations, adapter))]
fn resolve_udf_references(
    query_sql: &str,
    function_locations: &Bound<'_, PyAny>,
    adapter: &Bound<'_, PyAny>,
) -> PyResult<String> {
    resolve_function_calls(query_sql, function_locations, adapter, false)
}

#[pyfunction]
#[pyo3(signature = (*, query_sql, function_locations, adapter))]
fn resolve_table_function_references(
    query_sql: &str,
    function_locations: &Bound<'_, PyAny>,
    adapter: &Bound<'_, PyAny>,
) -> PyResult<String> {
    resolve_function_calls(query_sql, function_locations, adapter, true)
}

#[pyfunction]
#[pyo3(signature = (*, model_locations, seed_locations, deferred_locations, selected_keys))]
fn apply_deferred_locations<'py>(
    model_locations: &Bound<'py, PyDict>,
    seed_locations: &Bound<'py, PyDict>,
    deferred_locations: &Bound<'py, PyDict>,
    selected_keys: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyDict>, Bound<'py, PyDict>)> {
    let selected = selected_keys
        .try_iter()?
        .map(|key| key?.getattr("name")?.extract::<String>())
        .collect::<PyResult<std::collections::HashSet<_>>>()?;
    let models = model_locations.copy()?;
    let seeds = seed_locations.copy()?;
    for (name, target) in deferred_locations.iter() {
        if selected.contains(&name.extract::<String>()?) {
            continue;
        }
        if models.contains(&name)? {
            models.set_item(&name, &target)?;
        }
        if seeds.contains(&name)? {
            seeds.set_item(&name, &target)?;
        }
    }
    Ok((models, seeds))
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_ref_references, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_dbt_ref_references, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_udf_references, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_table_function_references, module)?)?;
    module.add_function(wrap_pyfunction!(apply_deferred_locations, module)?)?;
    Ok(())
}
