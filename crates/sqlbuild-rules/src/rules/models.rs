use std::cell::RefCell;
use std::collections::BTreeMap;

use crate::models::{EvaluateRequest, Fault, Model, RuleMetadata, RulesConfig};
use globset::GlobSet;

#[derive(Debug, Default)]
pub(crate) struct FaultCollector {
    faults: RefCell<Vec<Fault>>,
}

#[derive(Debug)]
pub(crate) struct ModelEvaluationRequest<'a> {
    pub(crate) model: &'a Model,
    pub(crate) config: &'a RulesConfig,
    pub(crate) selected: &'a BTreeMap<String, &'a RuleMetadata>,
    pub(crate) request: &'a EvaluateRequest,
    pub(crate) threshold_overrides: &'a [ResolvedThresholdOverride],
}

#[derive(Debug)]
pub(crate) struct ProjectEvaluationRequest<'a> {
    pub(crate) selected: &'a BTreeMap<String, &'a RuleMetadata>,
    pub(crate) request: &'a EvaluateRequest,
}

#[derive(Debug)]
pub(crate) struct ResolvedThresholdOverride {
    pub(crate) matcher: GlobSet,
    pub(crate) thresholds: BTreeMap<String, u32>,
}

impl ResolvedThresholdOverride {
    pub(crate) fn matches(&self, path: &str) -> bool {
        self.matcher.is_match(path)
    }

    pub(crate) fn threshold(&self, name: &str) -> Option<u32> {
        self.thresholds.get(name).copied()
    }
}

impl FaultCollector {
    pub(crate) fn push(&self, fault: Fault) {
        self.faults.borrow_mut().push(fault);
    }

    pub(crate) fn into_inner(self) -> Vec<Fault> {
        self.faults.into_inner()
    }
}

/// The value kind of one built-in rule option.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BuiltinOptionKind {
    /// A boolean defaulting to false.
    Boolean,
    /// A list of strings defaulting to empty.
    StringList,
}

/// One option a built-in rule declares.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BuiltinOption {
    pub kind: BuiltinOptionKind,
    pub name: &'static str,
    pub description: &'static str,
}
