//! Recorded fact reads and stored custom-rule caches.

use std::collections::BTreeMap;

use crate::custom_rule_cache::models::StoredRule;

/// One compiler fact a custom rule read, as its key parts.
pub type FactKey = Vec<String>;
/// The sorted, distinct facts one invocation read.
pub type ReadSet = Vec<FactKey>;
/// Every usable stored rule cache by rule code.
pub type StoredRules = BTreeMap<String, StoredRule>;
/// Results by `(rule code, subject key)`, each a list of finding payloads.
pub type SubjectResults = BTreeMap<(String, String), Vec<serde_json::Value>>;
