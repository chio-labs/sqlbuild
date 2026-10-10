//! Whether Python's syntax validation accepts every SQL string, stopping at the first it rejects.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::assembly::project::_helpers::syntax::syntax_valid;
use crate::assembly::project::models::SyntaxCheck;

/// Whether every check parses; Err is a deferral kind or a native failure.
pub fn check_sql_syntax(dialect: &str, checks: &[SyntaxCheck]) -> Result<bool, String> {
    catch_compiler_panic(|| all_valid(dialect, checks))
}

fn all_valid(dialect: &str, checks: &[SyntaxCheck]) -> Result<bool, String> {
    for check in checks {
        if !syntax_valid(check, dialect)? {
            return Ok(false);
        }
    }
    Ok(true)
}
