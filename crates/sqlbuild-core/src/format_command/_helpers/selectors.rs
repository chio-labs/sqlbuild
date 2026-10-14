//! Formatter path selector syntax shared by the selector entry points.

use crate::format_command::constants::{
    LINT_DIRECTORY_NAMES, PARENT_PATH_SEGMENT, PATH_GRAPH_MARKERS, PATH_SELECTOR_PREFIX,
    PATH_SEPARATOR,
};

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

/// One prefix per selector token, or `None` when any token needs graph selection.
pub(crate) fn lint_path_prefixes(raw_selectors: &[String]) -> Option<Vec<String>> {
    let mut prefixes: Vec<String> = Vec::new();
    for raw_selector in raw_selectors {
        if raw_selector.trim().is_empty() {
            return None;
        }
        for token in raw_selector.split_whitespace() {
            let normalized: String = token.replace('\\', "/");
            if !normalized.starts_with(PATH_SELECTOR_PREFIX) && !is_bare_lint_path(&normalized) {
                return None;
            }
            let prefix: &str = normalized
                .strip_prefix(PATH_SELECTOR_PREFIX)
                .unwrap_or(&normalized)
                .trim_matches(PATH_SEPARATOR);
            if prefix.contains(PATH_GRAPH_MARKERS) {
                return None;
            }
            let parts: Vec<&str> = prefix
                .split(PATH_SEPARATOR)
                .filter(|part| !part.is_empty())
                .collect();
            let valid_root: bool = parts
                .first()
                .is_some_and(|root| LINT_DIRECTORY_NAMES.contains(root));
            if !valid_root || parts.contains(&PARENT_PATH_SEGMENT) {
                return None;
            }
            prefixes.push(parts.join("/"));
        }
    }
    Some(prefixes)
}
