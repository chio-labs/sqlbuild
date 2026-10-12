//! Shell-style wildcard matching of one directory entry name.

use crate::text::_helpers::glob::wildcard_match;
use crate::text::main::ignorecase_key::ignorecase_key;

/// Whether `name` matches `pattern`, optionally ignoring case.
#[must_use]
pub fn glob_name_match(name: &str, pattern: &str, ignore_case: bool) -> bool {
    if !ignore_case {
        return wildcard_match(name, pattern);
    }
    let folded_name: String = name.chars().map(ignorecase_key).collect();
    let folded_pattern: String = pattern.chars().map(ignorecase_key).collect();
    wildcard_match(&folded_name, &folded_pattern)
}
