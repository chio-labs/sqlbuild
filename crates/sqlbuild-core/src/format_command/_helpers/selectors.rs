//! Formatter path selector syntax shared by the selector entry points.

use crate::format_command::constants::{LINT_DIRECTORY_NAMES, PATH_SEPARATOR};

/// `models/orders.sql`-style tokens are formatter paths without a `path:` prefix.
pub(crate) fn is_bare_lint_path(token: &str) -> bool {
    let first_segment: &str = token.split(PATH_SEPARATOR).next().unwrap_or_default();
    token.contains(PATH_SEPARATOR) && LINT_DIRECTORY_NAMES.contains(&first_segment)
}

/// Whether `relative_path` is one of `prefixes` or lies below one.
pub(crate) fn matches_path_prefix(relative_path: &str, prefixes: &[String]) -> bool {
    prefixes.iter().any(|prefix| {
        relative_path == prefix
            || relative_path
                .strip_prefix(prefix.as_str())
                .is_some_and(|rest| rest.starts_with(PATH_SEPARATOR))
    })
}
