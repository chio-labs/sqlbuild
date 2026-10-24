//! Authored SQL that names the reserved analysis function.

use crate::cursor_intrinsics::constants::RESERVED_ANALYSIS_FUNCTION;

/// The error for `context` when `sql` names the reserved analysis function in any case.
pub(crate) fn reserved_function_error(sql: &str, context: &str) -> Option<String> {
    let name: &[u8] = RESERVED_ANALYSIS_FUNCTION.as_bytes();
    sql.as_bytes()
        .windows(name.len())
        .any(|window| window.eq_ignore_ascii_case(name))
        .then(|| {
            format!(
                "{context} uses {RESERVED_ANALYSIS_FUNCTION}, a name reserved for SQL analysis; \
                 rename it"
            )
        })
}
