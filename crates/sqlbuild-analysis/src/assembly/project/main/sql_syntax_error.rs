//! Python's syntax validation message for one SQL string.

use crate::assembly::project::_helpers::syntax::syntax_error;
use crate::assembly::project::models::{SyntaxCheck, SyntaxFailure, SyntaxMode};

/// The message Python's validation raises with, None where Polyglot accepts the SQL.
pub fn sql_syntax_error(
    check: &SyntaxCheck,
    dialect: &str,
    mode: SyntaxMode,
) -> Result<Option<String>, SyntaxFailure> {
    syntax_error(check, dialect, mode)
}
