//! Names authored SQL may not use because analysis gives them a meaning of its own.

/// The analysis-only type assertion the SQL parser lowers into a typed expression.
pub const RESERVED_ANALYSIS_FUNCTION: &str = "__polyglot_typed";
