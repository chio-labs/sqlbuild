//! Boundary calls shared by reference and source resolution.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyString;
use sqlbuild_sqltext::resolution::main::cursor_subquery::cursor_subquery;
use sqlbuild_sqltext::resolution::models::CursorFilter;

pub(super) const NATIVE_MODULE: &str = "sqlbuild._native";

pub(super) fn string<'py>(py: Python<'py>, text: &str) -> Bound<'py, PyAny> {
    PyString::new(py, text).into_any()
}

pub(super) fn method<'py>(
    object: &Bound<'py, PyAny>,
    name: &str,
    values: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&object.getattr(name)?, values)
}

pub(super) fn cursor_wrap(
    arguments: &KeywordArguments<'_>,
    relation: String,
    name: &str,
    inject_alias: bool,
) -> PyResult<String> {
    let bounds = arguments.value("cursor_bounds")?;
    if bounds.is_none() {
        return Ok(relation);
    }
    let column: Option<String> = arguments
        .value("cursor_filter_inputs")?
        .call_method1("get", (name,))?
        .extract()?;
    let Some(column) = column else {
        return Ok(relation);
    };
    let adapter = arguments.value("adapter")?;
    let py = adapter.py();
    let cursor_type = arguments.value("cursor_type")?;
    let literal = |bound: &str| -> PyResult<String> {
        let token = call_with(
            &imported(py, NATIVE_MODULE, "cursor_sentinel_to_token")?,
            &[("sentinel", bounds.getattr(bound)?)],
        )?;
        method(
            &adapter,
            "render_cursor_bound_literal",
            &[("value", token), ("cursor_type", cursor_type.clone())],
        )?
        .extract()
    };
    let start = literal("start")?;
    let end = literal("end")?;
    let alias = inject_alias
        && adapter
            .call_method0("requires_derived_table_aliases")?
            .is_truthy()?;
    Ok(cursor_subquery(
        &relation,
        &CursorFilter {
            column: &column,
            start: &start,
            end: &end,
            lower_inclusive: arguments.value("lower_bound_inclusive")?.is_truthy()?,
            typed: !cursor_type.is_none(),
        },
        alias,
    ))
}
