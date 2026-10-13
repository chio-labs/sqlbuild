//! Formatter path prefixes of simple path selectors.

use crate::format_command::_helpers::selectors::is_bare_lint_path;
use crate::format_command::constants::{
    LINT_DIRECTORY_NAMES, PARENT_PATH_SEGMENT, PATH_GRAPH_MARKERS, PATH_SELECTOR_PREFIX,
    PATH_SEPARATOR,
};

/// One prefix per selector token, or `None` when any token needs graph selection.
#[must_use]
pub fn lint_path_prefixes(raw_selectors: &[String]) -> Option<Vec<String>> {
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
