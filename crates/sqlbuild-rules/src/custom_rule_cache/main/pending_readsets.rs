//! `pending_readsets`: the stored read sets whose current digest decides a cache hit.

use crate::custom_rule_cache::_helpers::current::{current_entry, current_rule};
use crate::custom_rule_cache::models::CustomRule;
use crate::custom_rule_cache::types::{ReadSet, StoredRules};

/// Distinct read sets of every reusable entry, in first-use order.
#[must_use]
pub fn pending_readsets(stored: &StoredRules, rules: &[CustomRule]) -> Vec<ReadSet> {
    let mut pending: Vec<ReadSet> = Vec::new();
    for rule in rules {
        let Some(cached) = current_rule(stored, rule) else {
            continue;
        };
        for subject in &rule.subjects {
            let readset: Option<&ReadSet> = current_entry(cached, &subject.key, &subject.identity)
                .and_then(|entry| cached.readsets.get(entry.readset));
            if let Some(readset) = readset.filter(|readset| !pending.contains(readset)) {
                pending.push(readset.clone());
            }
        }
    }
    pending
}
