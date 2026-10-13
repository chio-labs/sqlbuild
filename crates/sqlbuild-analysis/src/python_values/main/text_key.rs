//! A `str` dict key.

use crate::python_values::models::PythonKey;

/// The key of a `str` field name.
#[must_use]
pub fn text_key(text: &str) -> PythonKey {
    PythonKey {
        text: Ok(text.to_owned()),
        is_str: true,
    }
}
