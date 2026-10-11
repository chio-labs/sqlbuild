//! Whether Python's syntax validation accepts every SQL string, stopping at the first it rejects.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::assembly::project::_helpers::syntax::syntax_valid;
use crate::assembly::project::models::{SyntaxCheck, SyntaxFailure};

/// Whether every check parses, stopping at the first rejection or `ValueError`; Err is a panic.
pub fn check_sql_syntax(
    dialect: &str,
    checks: &[SyntaxCheck],
) -> Result<Result<bool, SyntaxFailure>, String> {
    catch_compiler_panic(|| Ok(all_valid(dialect, checks)))
}

fn all_valid(dialect: &str, checks: &[SyntaxCheck]) -> Result<bool, SyntaxFailure> {
    for check in checks {
        if !syntax_valid(check, dialect)? {
            return Ok(false);
        }
    }
    Ok(true)
}
