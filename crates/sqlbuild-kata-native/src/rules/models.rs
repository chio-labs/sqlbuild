use std::cell::RefCell;
use std::collections::BTreeMap;

use crate::models::{EvaluateRequest, Fault, KataConfig, Model, RuleMetadata};

#[derive(Debug, Default)]
pub(crate) struct FaultCollector {
    faults: RefCell<Vec<Fault>>,
}

#[derive(Debug)]
pub(crate) struct ModelEvaluationRequest<'a> {
    pub(crate) model: &'a Model,
    pub(crate) config: &'a KataConfig,
    pub(crate) selected: &'a BTreeMap<String, &'a RuleMetadata>,
    pub(crate) request: &'a EvaluateRequest,
    pub(crate) is_anchor: bool,
}

impl FaultCollector {
    pub(crate) fn push(&self, fault: Fault) {
        self.faults.borrow_mut().push(fault);
    }

    pub(crate) fn into_inner(self) -> Vec<Fault> {
        self.faults.into_inner()
    }
}
