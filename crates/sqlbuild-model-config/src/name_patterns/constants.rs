//! How a dynamic column family's `name_pattern` is anchored and described.

/// Anchors a pattern so it must match a whole column name, like Python's `re.fullmatch`.
pub(crate) const FULL_MATCH_PREFIX: &str = r"\A(?:";
pub(crate) const FULL_MATCH_SUFFIX: &str = r")\z";
/// The line of a regex syntax error that names the problem.
pub(crate) const SYNTAX_ERROR_PREFIX: &str = "error: ";
pub(crate) const TOO_LARGE_MESSAGE: &str = "the pattern is too large to compile";
