//! The polyglot dialect name a project's SQL analysis dialect selects.

use crate::assembly::analysis_session::_helpers::mappings;

/// Python's `NATIVE_DIALECT_ALIASES.get(dialect or "", dialect)`.
pub fn native_dialect(dialect: Option<&str>) -> Option<&str> {
    dialect.map(mappings::native_dialect)
}
