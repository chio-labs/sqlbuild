//! Custom-rule cache identity inputs, subjects, stored entries and evaluations.

use std::collections::BTreeMap;

use crate::custom_rule_cache::types::ReadSet;

/// Everything besides recorded fact reads that changes one custom rule's results.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RuleIdentityInput {
    pub code_identity: String,
    pub runtime_version: String,
    pub code: String,
    pub family: String,
    pub slug: String,
    pub message: String,
    pub remediation: String,
    pub subject: Option<String>,
    pub implementation_fingerprint: String,
    pub config_json: String,
    pub dialect: String,
    pub project_dir: String,
}

/// One model as a custom-rule subject: path, name and materialization.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ModelSubjectInput {
    pub path: String,
    pub name: String,
    pub materialized: Option<String>,
}

/// The project facts that decide which subjects custom rules run on.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SubjectsInput {
    pub target_name: Option<String>,
    pub models: Vec<ModelSubjectInput>,
}

/// One rule invocation's subject: its key and an identity of the subject's own metadata.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Subject {
    pub key: String,
    pub identity: String,
}

/// One selected custom rule, its identity when caching, subject kind and subjects.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CustomRule {
    pub code: String,
    pub identity: Option<String>,
    pub subject: Option<String>,
    pub subjects: Vec<Subject>,
}

/// One stored invocation result and the read set digest it was valid for.
#[derive(Clone, Debug, PartialEq)]
pub struct StoredEntry {
    pub subject_identity: String,
    pub readset: usize,
    pub reads_digest: String,
    pub findings: Vec<serde_json::Value>,
}

/// One rule's stored results, sharing read sets between subjects.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct StoredRule {
    pub identity: String,
    pub readsets: Vec<ReadSet>,
    pub entries: BTreeMap<String, StoredEntry>,
}

/// Reused results, the subjects each rule must still evaluate (`None` for all) and counts.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct CustomCacheLookup {
    pub hits: Vec<((String, String), Vec<serde_json::Value>)>,
    pub plan: BTreeMap<String, Option<Vec<String>>>,
    pub hit_count: usize,
    pub miss_count: usize,
}

/// One evaluated invocation, with its read set and digest when its result may be cached.
#[derive(Clone, Debug, PartialEq)]
pub struct CustomEvaluation {
    pub code: String,
    pub subject: String,
    pub cacheable: Option<(ReadSet, Option<String>)>,
    pub findings: Vec<serde_json::Value>,
}
