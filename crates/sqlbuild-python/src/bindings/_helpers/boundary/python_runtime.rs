//! Record the running Python's string semantics for native text helpers.

use pyo3::prelude::{PyAnyMethods, PyResult, Python};
use sqlbuild_core::text::main::active_python_text::set_active_python_text;
use sqlbuild_core::text::main::python_text::python_text;

/// Select the running Python's `str` semantics; an unsupported Python fails at discovery instead.
pub(crate) fn record_python_text(python: Python<'_>) -> PyResult<()> {
    let version: (u8, u8) = python
        .import("sys")?
        .getattr("version_info")?
        .extract::<(u8, u8, u8, String, u8)>()
        .map(|(major, minor, ..)| (major, minor))?;
    let unicode_version: String = python
        .import("unicodedata")?
        .getattr("unidata_version")?
        .extract()?;
    if let Some(text) = python_text(version, &unicode_version) {
        set_active_python_text(text);
    }
    Ok(())
}
