//! `Path.glob` name matching for the discovery directory snapshot.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyAnyMethods, PyString, PyStringMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::text::main::python_glob_name_match::python_glob_name_match;

const ENCODE: &str = "encode";
const UTF32_LE: &str = "utf-32-le";
const SURROGATE_PASS: &str = "surrogatepass";

/// The code points of `name`; undecodable file names keep their lone surrogates.
fn code_points(name: &Bound<'_, PyString>) -> PyResult<Vec<u32>> {
    match name.to_str() {
        Ok(text) => Ok(text.chars().map(u32::from).collect()),
        Err(_) => Ok(name
            .call_method1(ENCODE, (UTF32_LE, SURROGATE_PASS))?
            .extract::<Vec<u8>>()?
            .as_chunks::<4>()
            .0
            .iter()
            .map(|unit| u32::from_le_bytes([unit[0], unit[1], unit[2], unit[3]]))
            .collect()),
    }
}

/// Whether a directory entry name matches a single-name glob `pattern`.
#[pyfunction]
fn glob_name_match(name: &Bound<'_, PyString>, pattern: &str, ignore_case: bool) -> PyResult<bool> {
    Ok(python_glob_name_match(
        &code_points(name)?,
        pattern,
        ignore_case,
    ))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(glob_name_match, module)?)
}
