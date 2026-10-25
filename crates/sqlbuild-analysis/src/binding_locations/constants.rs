//! Binding codes and severities the location pass reads.

/// The internal unknown-table code, which compile never reports.
pub(crate) const UNKNOWN_TABLE_INTERNAL_CODE: &str = "B000";
/// The severity whose repeats at a known span compile drops.
pub(crate) const ERROR_SEVERITY: &str = "error";
/// SQLite temporal-cast warnings, which every binding pass reports, so they are kept once.
pub(crate) const SQLITE_TEMPORAL_CAST_CODE: &str = "B104";
