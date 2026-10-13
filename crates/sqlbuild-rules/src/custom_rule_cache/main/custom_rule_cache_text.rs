//! `custom_rule_cache_text`: the stored form of the custom-rule result cache.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Map, Value, json};

use crate::custom_rule_cache::constants::{
    CACHE_VERSION, ENTRIES_KEY, IDENTITY_KEY, READSETS_KEY, RULES_KEY, VERSION_KEY,
};
use crate::custom_rule_cache::models::{CustomRule, StoredRule};
use crate::custom_rule_cache::types::StoredRules;

fn rule_value(cached: &StoredRule, rule: &CustomRule) -> Value {
    let live: BTreeSet<&str> = rule
        .subjects
        .iter()
        .map(|subject| subject.key.as_str())
        .collect();
    let used: BTreeSet<usize> = cached
        .entries
        .iter()
        .filter(|(key, _)| live.contains(key.as_str()))
        .map(|(_, entry)| entry.readset)
        .collect();
    let remap: BTreeMap<usize, usize> = used
        .iter()
        .enumerate()
        .map(|(new, old)| (*old, new))
        .collect();
    let entries: Map<String, Value> = cached
        .entries
        .iter()
        .filter_map(|(key, entry)| {
            let index: usize = *remap.get(&entry.readset)?;
            let value = json!([
                entry.subject_identity,
                index,
                entry.reads_digest,
                entry.findings
            ]);
            live.contains(key.as_str()).then(|| (key.clone(), value))
        })
        .collect();
    let readsets: Vec<Value> = used
        .iter()
        .filter_map(|index| cached.readsets.get(*index))
        .map(|readset| json!(readset))
        .collect();
    json!({ IDENTITY_KEY: cached.identity, READSETS_KEY: readsets, ENTRIES_KEY: entries })
}

/// Compact JSON of the format version and each selected rule's live subjects and read sets.
#[must_use]
pub fn custom_rule_cache_text(stored: &StoredRules, rules: &[CustomRule]) -> String {
    let stored_rules: Map<String, Value> = rules
        .iter()
        .filter_map(|rule| Some((rule.code.clone(), rule_value(stored.get(&rule.code)?, rule))))
        .collect();
    json!({ VERSION_KEY: CACHE_VERSION, RULES_KEY: stored_rules }).to_string()
}
