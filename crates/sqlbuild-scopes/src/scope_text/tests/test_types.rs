use crate::scope_report::models::ScopeResult;
use crate::scope_text::models::ScopeTextRequest;

pub(super) struct ScopeTextTestCase {
    pub(super) description: &'static str,
    pub(super) result: ScopeResult,
    pub(super) request: ScopeTextRequest,
    pub(super) expected_text: &'static str,
    pub(super) expected_failed: bool,
}
