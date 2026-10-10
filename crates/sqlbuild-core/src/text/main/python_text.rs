//! Select the Python string semantics of one CPython release.

use crate::text::_helpers::alnum_tables::{ALNUM_TABLES, ALPHA_TABLES, DECIMAL_TABLES};
use crate::text::models::{CleandocMargin, PythonText};

/// The semantics of one Python and its `unicodedata.unidata_version`, or `None` if unknown.
pub fn python_text(python_version: (u8, u8), unicode_version: &str) -> Option<PythonText> {
    let cleandoc_margin: CleandocMargin = match python_version {
        (3, 12) => CleandocMargin::Whitespace,
        (3, 13 | 14) => CleandocMargin::Spaces,
        _ => return None,
    };
    let alnum_ranges: &'static [(u32, u32)] = ALNUM_TABLES
        .iter()
        .find(|(version, _)| *version == unicode_version)
        .map(|(_, ranges)| *ranges)?;
    let alpha_ranges: &'static [(u32, u32)] = ALPHA_TABLES
        .iter()
        .find(|(version, _)| *version == unicode_version)
        .map(|(_, ranges)| *ranges)?;
    let decimal_ranges: &'static [(u32, u32)] = DECIMAL_TABLES
        .iter()
        .find(|(version, _)| *version == unicode_version)
        .map(|(_, ranges)| *ranges)?;
    Some(PythonText {
        alnum_ranges,
        alpha_ranges,
        decimal_ranges,
        cleandoc_margin,
        minor_version: python_version.1,
    })
}
