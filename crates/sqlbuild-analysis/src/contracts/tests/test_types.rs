use crate::contracts::models::{ContractModel, PromotionRequest};

pub(crate) struct ContractTestCase {
    pub(crate) description: &'static str,
    pub(crate) implicit: bool,
    pub(crate) model: ContractModel,
    /// One `code severity location message` line per diagnostic, or `deferred:<kind>`.
    pub(crate) expected_lines: &'static [&'static str],
}

pub(crate) struct PromotionTestCase {
    pub(crate) description: &'static str,
    pub(crate) request: PromotionRequest,
    pub(crate) expected_models: &'static [usize],
    pub(crate) expected_help: Option<&'static str>,
}
