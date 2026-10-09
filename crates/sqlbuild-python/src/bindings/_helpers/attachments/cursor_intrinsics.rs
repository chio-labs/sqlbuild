//! Cursor intrinsic validation, rejection and rendering.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyString, PyStringMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_attachments::cursor_intrinsics::main::intrinsic_free::intrinsic_free;
use sqlbuild_attachments::cursor_intrinsics::main::replace_intrinsics::replace_intrinsics;
use sqlbuild_attachments::cursor_intrinsics::main::validated_model_intrinsics::{
    IntrinsicModel, validated_model_intrinsics,
};
use sqlbuild_attachments::cursor_intrinsics::models::IntrinsicCheck;
use sqlbuild_core::text::models::PythonText;

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::discovery::project_files::python_semantics;

const INCREMENTAL_MATERIALIZATION: &str = "incremental";
const CURSOR_START: &str = "__cursor_start";

/// The running Python's version and `unicodedata.unidata_version`.
type PythonRelease = ((u8, u8), String);

fn semantics((version, unicode): PythonRelease) -> PyResult<PythonText> {
    python_semantics(version, &unicode)
}

/// `None` if `sql` is free of cursor intrinsics and reserved markers, else the error for `context`.
#[pyfunction]
fn cursor_intrinsics_rejection(
    sql: &str,
    reserved_markers: Vec<String>,
    context: &str,
    python: PythonRelease,
) -> PyResult<Option<String>> {
    let python: PythonText = semantics(python)?;
    compiler_guard(|| {
        Ok(
            match intrinsic_free(python, sql, &reserved_markers, context) {
                IntrinsicCheck::Free => None,
                IntrinsicCheck::Rejected(message) => Some(message),
            },
        )
    })
}

/// A model query with canonical intrinsic calls and no error, or no query and the error.
#[pyfunction]
fn validated_model_cursor_intrinsics(
    sql: &str,
    reserved_markers: Vec<String>,
    model: (String, Bound<'_, PyAny>, Bound<'_, PyAny>),
    python: PythonRelease,
) -> PyResult<(Option<String>, Option<String>)> {
    let python: PythonText = semantics(python)?;
    let (name, materialized, cursor) = model;
    let incremental: bool = materialized
        .downcast::<PyString>()
        .is_ok_and(|text| text.to_string_lossy() == INCREMENTAL_MATERIALIZATION);
    let cursor: Option<String> = cursor
        .downcast::<PyString>()
        .ok()
        .map(|text| text.to_string_lossy().into_owned());
    compiler_guard(|| {
        Ok(
            match validated_model_intrinsics(
                python,
                sql,
                &reserved_markers,
                &IntrinsicModel {
                    name: &name,
                    incremental,
                    cursor: cursor.as_deref(),
                },
            ) {
                Ok(canonical) => (Some(canonical), None),
                Err(message) => (None, Some(message)),
            },
        )
    })
}

/// `sql` with intrinsic calls replaced by the start and end SQL, whether any was, and no error;
/// or the error for `context`.
#[pyfunction]
fn replace_cursor_intrinsics(
    sql: &str,
    context: &str,
    replacements: (String, String),
    python: PythonRelease,
) -> PyResult<(String, bool, Option<String>)> {
    let python: PythonText = semantics(python)?;
    let (start, end) = replacements;
    compiler_guard(|| {
        Ok(
            match replace_intrinsics(python, sql, context, |name| {
                if name == CURSOR_START {
                    start.clone()
                } else {
                    end.clone()
                }
            }) {
                Ok((replaced, found)) => (replaced, found, None),
                Err(message) => (String::new(), false, Some(message)),
            },
        )
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(cursor_intrinsics_rejection, module)?)?;
    module.add_function(wrap_pyfunction!(validated_model_cursor_intrinsics, module)?)?;
    module.add_function(wrap_pyfunction!(replace_cursor_intrinsics, module)?)?;
    Ok(())
}
