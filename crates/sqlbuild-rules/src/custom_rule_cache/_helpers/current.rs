//! The stored results that still belong to the current rule and subject identities.

use crate::custom_rule_cache::models::{CustomRule, StoredEntry, StoredRule};
use crate::custom_rule_cache::types::StoredRules;

/// The stored rule cache of `rule` when its identity is unchanged.
pub(crate) fn current_rule<'a>(
    stored: &'a StoredRules,
    rule: &CustomRule,
) -> Option<&'a StoredRule> {
    let cached: &StoredRule = stored.get(&rule.code)?;
    (rule.identity.as_deref() == Some(cached.identity.as_str())).then_some(cached)
}

/// The stored entry for one subject when its identity is unchanged.
pub(crate) fn current_entry<'a>(
    cached: &'a StoredRule,
    key: &str,
    identity: &str,
) -> Option<&'a StoredEntry> {
    cached
        .entries
        .get(key)
        .filter(|entry| entry.subject_identity == identity)
}
