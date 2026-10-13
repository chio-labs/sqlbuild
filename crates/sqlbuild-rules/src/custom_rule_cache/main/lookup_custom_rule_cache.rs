//! `lookup_custom_rule_cache`: reuse results whose recorded fact reads still digest the same.

use std::collections::BTreeMap;

use crate::custom_rule_cache::_helpers::current::{current_entry, current_rule};
use crate::custom_rule_cache::models::{CustomCacheLookup, CustomRule, StoredEntry, StoredRule};
use crate::custom_rule_cache::types::{ReadSet, StoredRules};

fn reusable<'a>(
    cached: Option<&'a StoredRule>,
    rule_subject: (&str, &str),
    digests: &BTreeMap<ReadSet, String>,
) -> Option<&'a StoredEntry> {
    let cached: &StoredRule = cached?;
    let entry: &StoredEntry = current_entry(cached, rule_subject.0, rule_subject.1)?;
    let readset: &ReadSet = cached.readsets.get(entry.readset)?;
    (digests.get(readset) == Some(&entry.reads_digest)).then_some(entry)
}

/// Hits per rule and subject, and each rule's missing subjects (`None` when all miss).
#[must_use]
pub fn lookup_custom_rule_cache(
    stored: &StoredRules,
    rules: &[CustomRule],
    digests: &BTreeMap<ReadSet, String>,
) -> CustomCacheLookup {
    let mut lookup = CustomCacheLookup::default();
    for rule in rules {
        let cached: Option<&StoredRule> = current_rule(stored, rule);
        let mut missing: Vec<String> = Vec::new();
        for subject in &rule.subjects {
            match reusable(cached, (&subject.key, &subject.identity), digests) {
                Some(entry) => {
                    let key = (rule.code.clone(), subject.key.clone());
                    lookup.hits.push((key, entry.findings.clone()));
                    lookup.hit_count += 1;
                }
                None => missing.push(subject.key.clone()),
            }
        }
        if missing.is_empty() {
            continue;
        }
        lookup.miss_count += missing.len();
        let planned: Option<Vec<String>> = if missing.len() == rule.subjects.len() {
            None
        } else {
            missing.sort();
            Some(missing)
        };
        lookup.plan.insert(rule.code.clone(), planned);
    }
    lookup
}
