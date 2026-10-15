//! Prefixes, statements and widths of `--debug` console lines.

/// The logger prefix diagnostics console headers drop from SQLBuild logger names.
pub(crate) const DIAGNOSTIC_LOGGER_PREFIX: &str = "sqlbuild.";
/// Statements a diagnostics console line shows inline instead of in a block.
pub(crate) const INLINE_SQL_STATEMENTS: [&str; 3] = ["BEGIN", "COMMIT", "ROLLBACK"];
/// The rule above and below a block of logged SQL.
pub(crate) const SQL_SEPARATOR_WIDTH: usize = 80;
