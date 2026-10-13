//! `file_rule_key`: the cache key of one non-model SQL file's rule findings.

use crate::rule_cache::_helpers::digest::field_digest;
use crate::rule_cache::constants::{FILE_KEY_KIND, MACRO_TOKEN, TEMPLATE_INTERPOLATION_START};

/// A digest of the lint key, codes, path and text; `None` when macros or templates expand it.
#[must_use]
pub fn file_rule_key(
    lint_key: &str,
    codes: &[String],
    (relative_path, contents): (&str, &str),
    expanded: bool,
) -> Option<String> {
    if expanded || contents.contains(MACRO_TOKEN) || contents.contains(TEMPLATE_INTERPOLATION_START)
    {
        return None;
    }
    let codes: String = codes.join("\0");
    Some(field_digest(
        FILE_KEY_KIND,
        &[lint_key, &codes, relative_path, contents],
    ))
}
