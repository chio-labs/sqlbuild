//! Running execution history SQL through a Python DB-API connection or cursor.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyTuple;
use sqlbuild_state::execution_history::models::{Query, SqlParam};

use crate::bindings::_helpers::execution_history::conversion::python_params;

/// `target.execute(sql, params)`.
pub(crate) fn execute<'py>(
    target: &Bound<'py, PyAny>,
    sql: &str,
    params: &[SqlParam],
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = target.py();
    target.call_method1("execute", (sql, python_params(py, params)?))
}

/// `target.execute(sql)` without parameters.
pub(crate) fn execute_plain<'py>(
    target: &Bound<'py, PyAny>,
    sql: &str,
) -> PyResult<Bound<'py, PyAny>> {
    target.call_method1("execute", (sql,))
}

/// `target.execute(query.sql, query.params)`.
pub(crate) fn execute_query<'py>(
    target: &Bound<'py, PyAny>,
    query: &Query,
) -> PyResult<Bound<'py, PyAny>> {
    execute(target, &query.sql, &query.params)
}

/// The first row `cursor.fetchone()` returns, or `None`.
pub(crate) fn fetch_one<'py>(cursor: &Bound<'py, PyAny>) -> PyResult<Option<Bound<'py, PyAny>>> {
    let row: Bound<'py, PyAny> = cursor.call_method0("fetchone")?;
    Ok((!row.is_none()).then_some(row))
}

/// Every row `cursor.fetchall()` returns.
pub(crate) fn fetch_all<'py>(cursor: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    cursor.call_method0("fetchall")?.try_iter()?.collect()
}

/// Run `body` while holding the Python `lock`, releasing it on every exit.
pub(crate) fn locked<T>(
    lock: &Bound<'_, PyAny>,
    body: impl FnOnce() -> PyResult<T>,
) -> PyResult<T> {
    lock.call_method0("acquire")?;
    let result: PyResult<T> = body();
    let released = lock.call_method0("release");
    let value: T = result?;
    released?;
    Ok(value)
}

/// `row[name]`.
pub(crate) fn column<'py>(row: &Bound<'py, PyAny>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    row.get_item(name)
}

/// The tuple of `items`.
pub(crate) fn tuple_of<'py>(
    py: Python<'py>,
    items: Vec<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(py, items)
}
