//! `store_custom_results`: merge newly evaluated results into the stored rule caches.

use std::collections::BTreeMap;

use crate::custom_rule_cache::models::{CustomEvaluation, CustomRule, StoredEntry, StoredRule};
use crate::custom_rule_cache::types::StoredRules;

fn store_one(
    mut current: StoredRule,
    subject_identity: &str,
    evaluation: &CustomEvaluation,
) -> StoredRule {
    let Some((readset, Some(digest))) = &evaluation.cacheable else {
        current.entries.remove(&evaluation.subject);
        return current;
    };
    let index: usize = match current.readsets.iter().position(|known| known == readset) {
        Some(index) => index,
        None => {
            current.readsets.push(readset.clone());
            current.readsets.len() - 1
        }
    };
    let entry = StoredEntry {
        subject_identity: subject_identity.to_owned(),
        readset: index,
        reads_digest: digest.clone(),
        findings: evaluation.findings.clone(),
    };
    current.entries.insert(evaluation.subject.clone(), entry);
    current
}

/// Stored caches of the selected rules, with stale rule identities reset and new results stored.
#[must_use]
pub fn store_custom_results(
    stored: &StoredRules,
    rules: &[CustomRule],
    evaluations: &[CustomEvaluation],
) -> StoredRules {
    let mut updated = StoredRules::new();
    for rule in rules {
        let Some(identity) = &rule.identity else {
            continue;
        };
        let mut current: StoredRule = stored
            .get(&rule.code)
            .filter(|previous| previous.identity == *identity)
            .cloned()
            .unwrap_or_else(|| StoredRule {
                identity: identity.clone(),
                ..StoredRule::default()
            });
        let subjects: BTreeMap<&str, &str> = rule
            .subjects
            .iter()
            .map(|subject| (subject.key.as_str(), subject.identity.as_str()))
            .collect();
        for evaluation in evaluations.iter().filter(|item| item.code == rule.code) {
            if let Some(subject_identity) = subjects.get(evaluation.subject.as_str()) {
                current = store_one(current, subject_identity, evaluation);
            }
        }
        updated.insert(rule.code.clone(), current);
    }
    updated
}
