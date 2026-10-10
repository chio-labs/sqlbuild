//! Record the running Python's string semantics for native text helpers.

use crate::text::_helpers::active_text;
use crate::text::models::PythonText;

/// Record the running Python's semantics; later calls keep the first value.
pub fn set_active_python_text(python: PythonText) {
    active_text::record(python);
}
