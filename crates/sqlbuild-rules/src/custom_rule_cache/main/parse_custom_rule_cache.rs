//! `parse_custom_rule_cache`: the usable rule caches of a stored custom-rule cache.

use serde_json::Value;

use crate::custom_rule_cache::_helpers::stored::stored_rule;
use crate::custom_rule_cache::constants::{CACHE_VERSION, RULES_KEY, VERSION_KEY};
use crate::custom_rule_cache::types::StoredRules;

/// Rule caches written by this format; malformed rules are skipped and anything else is empty.
#[must_use]
pub fn parse_custom_rule_cache(text: &str) -> StoredRules {
    let Ok(Value::Object(payload)) = serde_json::from_str::<Value>(text) else {
        return StoredRules::new();
    };
    if payload.get(VERSION_KEY).and_then(Value::as_str) != Some(CACHE_VERSION) {
        return StoredRules::new();
    }
    let Some(Value::Object(rules)) = payload.get(RULES_KEY) else {
        return StoredRules::new();
    };
    rules
        .iter()
        .filter_map(|(code, value)| Some((code.clone(), stored_rule(value)?)))
        .collect()
}
