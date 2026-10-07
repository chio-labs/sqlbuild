//! Python's `unsupported_keys_help`: nearest supported key suggestions.

use sqlbuild_core::text::main::close_matches::close_matches;

const SUGGESTION_CUTOFF: f64 = 0.6;
const LISTED_SUPPORTED_KEYS_LIMIT: usize = 12;

pub(crate) fn unsupported_keys_help(keys: &[&str], supported_keys: &[String]) -> String {
    let mut candidates: Vec<&str> = supported_keys.iter().map(String::as_str).collect();
    candidates.sort_unstable();
    candidates.dedup();
    let suggestions: Vec<String> = keys
        .iter()
        .filter_map(|key| suggestion(key, keys.len(), &candidates))
        .collect();
    if !suggestions.is_empty() {
        return format!("did you mean {}?", suggestions.join(", "));
    }
    if candidates.len() <= LISTED_SUPPORTED_KEYS_LIMIT {
        return format!("supported keys: {}", candidates.join(", "));
    }
    "remove the key; see the reference for supported keys".to_owned()
}

fn suggestion(key: &str, key_count: usize, candidates: &[&str]) -> Option<String> {
    let matched: String = close_matches(key, candidates, 1, SUGGESTION_CUTOFF)
        .into_iter()
        .next()?;
    if key_count == 1 {
        return Some(format!("'{matched}'"));
    }
    Some(format!("'{matched}' for '{key}'"))
}
