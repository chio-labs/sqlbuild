//! Cursor intrinsic rejection for SQL outside cursor-based incremental models.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_attachments::cursor_intrinsics::main::intrinsic_free::intrinsic_free;
use sqlbuild_attachments::cursor_intrinsics::models::IntrinsicCheck;

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// `(True, None)` if Python accepts `sql`, `(False, error)` if it rejects it, else `(False, None)`.
#[pyfunction]
fn sql_free_of_cursor_intrinsics(
    sql: &str,
    reserved_markers: Vec<String>,
    context: &str,
) -> PyResult<(bool, Option<String>)> {
    compiler_guard(|| {
        Ok(match intrinsic_free(sql, &reserved_markers, context) {
            IntrinsicCheck::Free => (true, None),
            IntrinsicCheck::Rejected(message) => (false, Some(message)),
            IntrinsicCheck::Deferred => (false, None),
        })
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(sql_free_of_cursor_intrinsics, module)?)?;
    Ok(())
}
