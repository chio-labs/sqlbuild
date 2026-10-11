//! The running Python's string semantics, recorded once per process.

use std::sync::OnceLock;

use crate::text::_helpers::alnum_tables::{
    ALNUM_TABLES, ALPHA_TABLES, DECIMAL_TABLES, PRINTABLE_TABLES,
};
use crate::text::_helpers::case_tables::{CASEFOLD_TABLES, IGNORECASE_KEY_TABLES, UPPER_TABLES};
use crate::text::models::{CleandocMargin, PythonText};

static ACTIVE: OnceLock<PythonText> = OnceLock::new();

/// Record the running Python's semantics; later calls keep the first value.
pub(crate) fn record(python: PythonText) {
    let _ = ACTIVE.set(python);
}

/// The recorded semantics, or Python 3.12's where none were recorded.
pub(crate) fn active() -> PythonText {
    *ACTIVE.get_or_init(|| PythonText {
        alnum_ranges: ALNUM_TABLES[0].1,
        alpha_ranges: ALPHA_TABLES[0].1,
        decimal_ranges: DECIMAL_TABLES[0].1,
        printable_ranges: PRINTABLE_TABLES[0].1,
        casefold_mappings: CASEFOLD_TABLES[0].1,
        upper_mappings: UPPER_TABLES[0].1,
        ignorecase_keys: IGNORECASE_KEY_TABLES[0].1,
        cleandoc_margin: CleandocMargin::Whitespace,
        minor_version: 12,
    })
}
