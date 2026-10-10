//! The running Python's string semantics, set once by the extension module.

use std::sync::OnceLock;

use crate::text::_helpers::alnum_tables::{ALNUM_TABLES, ALPHA_TABLES, DECIMAL_TABLES};
use crate::text::_helpers::case_tables::{CASEFOLD_TABLES, IGNORECASE_KEY_TABLES, UPPER_TABLES};
use crate::text::models::{CleandocMargin, PythonText};

static ACTIVE: OnceLock<PythonText> = OnceLock::new();

/// Record the running Python's semantics; later calls keep the first value.
pub fn set_active_python_text(python: PythonText) {
    let _ = ACTIVE.set(python);
}

/// The running Python's semantics; Rust-only callers that never set them get Python 3.12's.
pub fn active_python_text() -> PythonText {
    *ACTIVE.get_or_init(|| PythonText {
        alnum_ranges: ALNUM_TABLES[0].1,
        alpha_ranges: ALPHA_TABLES[0].1,
        decimal_ranges: DECIMAL_TABLES[0].1,
        casefold_mappings: CASEFOLD_TABLES[0].1,
        upper_mappings: UPPER_TABLES[0].1,
        ignorecase_keys: IGNORECASE_KEY_TABLES[0].1,
        cleandoc_margin: CleandocMargin::Whitespace,
        minor_version: 12,
    })
}
