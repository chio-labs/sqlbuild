use crate::terminal_events::models::{TerminalFact, TerminalRequest};

pub(super) struct ClaimTestCase {
    pub(super) description: &'static str,
    pub(super) facts: Vec<TerminalFact>,
    pub(super) requests: Vec<TerminalRequest>,
    pub(super) expected_claims: Vec<Option<usize>>,
    pub(super) expected_latest: Option<usize>,
}

pub(super) struct LifecycleTestCase {
    pub(super) description: &'static str,
    pub(super) facts: Vec<TerminalFact>,
    pub(super) expected_terminal: Option<usize>,
}
