//! Case-sensitive shell-style wildcard matching.

use crate::text::_helpers::glob::wildcard_match;

/// Whether `name` matches the shell-style `pattern`, case-sensitively and across newlines.
#[must_use]
pub fn glob_match(name: &str, pattern: &str) -> bool {
    wildcard_match(name, pattern)
}
