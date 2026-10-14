//! Plain model names of selectors that need no graph resolution.

use std::collections::BTreeSet;

use crate::format_command::constants::GRAPH_SELECTOR_MARKERS;

/// Every selector token as a model name, or `None` when canonical graph resolution is required.
#[must_use]
pub fn exact_selector_names(raw_selectors: &[String]) -> Option<BTreeSet<String>> {
    let mut names: BTreeSet<String> = BTreeSet::new();
    for raw_selector in raw_selectors {
        if raw_selector.trim().is_empty() {
            return None;
        }
        for token in raw_selector.split_whitespace() {
            if token.contains(GRAPH_SELECTOR_MARKERS) {
                return None;
            }
            names.insert(token.to_owned());
        }
    }
    Some(names)
}
