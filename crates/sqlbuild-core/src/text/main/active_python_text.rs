//! The running Python's string semantics, set once by the extension module.

use crate::text::_helpers::active_text;
use crate::text::models::PythonText;

/// The running Python's semantics; Rust-only callers that never set them get Python 3.12's.
pub fn active_python_text() -> PythonText {
    active_text::active()
}
