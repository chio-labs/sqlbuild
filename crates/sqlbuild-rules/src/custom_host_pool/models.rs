//! One host's reported results and the results merged across hosts.

use std::collections::{BTreeMap, BTreeSet};

use crate::custom_host_pool::types::FactKey;

/// The kind of subject a custom rule evaluates.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HostRuleSubject {
    Project,
    Model,
    Other,
}

/// One evaluated invocation: its findings and, when tracked, the facts it read.
#[derive(Clone, Debug, PartialEq)]
pub struct HostEvaluation {
    pub code: String,
    pub subject: String,
    pub findings: Vec<serde_json::Value>,
    pub reads: Option<Vec<FactKey>>,
}

/// What one host reported for its share of the plan.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct HostSlice {
    pub evaluations: Vec<HostEvaluation>,
    pub untracked_reads: BTreeMap<String, Vec<FactKey>>,
    pub uncacheable: BTreeSet<String>,
    pub observed: BTreeMap<FactKey, Option<String>>,
    pub bounded: bool,
    pub stateful: BTreeSet<String>,
}

/// Every host's results combined exactly as one host would have reported them.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct HostRun {
    pub evaluated: Vec<HostEvaluation>,
    pub untracked_reads: BTreeMap<String, Vec<FactKey>>,
    pub uncacheable: BTreeSet<String>,
    pub observed: BTreeMap<FactKey, Option<String>>,
}
