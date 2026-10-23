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
    pub timings: HostTimings,
}

/// One rule's invocations and the CPU nanoseconds they took, excluding runtime-guard checks.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct RuleTiming {
    pub invocations: u64,
    pub cpu_ns: u64,
}

/// Where host CPU went: each rule, the module-state monitor and the runtime guard's checks.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct HostTimings {
    pub rules: BTreeMap<String, RuleTiming>,
    pub monitor_ns: u64,
    pub guard_ns: u64,
}

impl HostTimings {
    /// Add `other`'s invocations and CPU to these timings.
    pub fn add(&mut self, other: &Self) {
        for (code, timing) in &other.rules {
            let total: &mut RuleTiming = self.rules.entry(code.clone()).or_default();
            total.invocations += timing.invocations;
            total.cpu_ns += timing.cpu_ns;
        }
        self.monitor_ns += other.monitor_ns;
        self.guard_ns += other.guard_ns;
    }
}

/// Every host's results combined exactly as one host would have reported them.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct HostRun {
    pub evaluated: Vec<HostEvaluation>,
    pub untracked_reads: BTreeMap<String, Vec<FactKey>>,
    pub uncacheable: BTreeSet<String>,
    pub observed: BTreeMap<FactKey, Option<String>>,
    /// Every host's timings summed, including hosts whose results a rerun replaced.
    pub timings: HostTimings,
}
