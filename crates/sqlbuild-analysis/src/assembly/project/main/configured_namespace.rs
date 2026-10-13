//! `_str_or_none`: a configured database or schema name, stripped, when it names one.

use sqlbuild_core::text::main::python_strip::python_strip;

/// Python's `value.strip() if value.strip() else None` for a string `value`.
pub fn configured_namespace(value: &str) -> Option<String> {
    let stripped: &str = python_strip(value);
    (!stripped.is_empty()).then(|| stripped.to_owned())
}
