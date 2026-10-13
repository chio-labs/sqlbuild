//! `ordered_custom_findings`: custom findings in rule code, then subject order.

use serde_json::Value;

use crate::custom_rule_cache::models::CustomRule;
use crate::custom_rule_cache::types::SubjectResults;

/// Every result's findings, rule by rule and subject by subject.
#[must_use]
pub fn ordered_custom_findings(rules: &[CustomRule], results: &SubjectResults) -> Vec<Value> {
    let mut findings: Vec<Value> = Vec::new();
    for rule in rules {
        for subject in &rule.subjects {
            if let Some(values) = results.get(&(rule.code.clone(), subject.key.clone())) {
                findings.extend(values.iter().cloned());
            }
        }
    }
    findings
}
