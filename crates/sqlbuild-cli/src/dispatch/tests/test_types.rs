use crate::dispatch::models::{CommandFacts, Dispatch, ExportSummary, InvocationPolicy};

pub(super) struct CommandDispatchTestCase {
    pub(super) description: &'static str,
    pub(super) facts: CommandFacts,
    pub(super) expected_dispatch: Dispatch,
}

pub(super) struct InvocationPolicyTestCase {
    pub(super) description: &'static str,
    pub(super) facts: CommandFacts,
    pub(super) expected_policy: InvocationPolicy,
}

pub(super) struct EventExportWarningTestCase {
    pub(super) description: &'static str,
    pub(super) summary: ExportSummary,
    pub(super) command_succeeded: bool,
    pub(super) expected_warning: Option<&'static str>,
}

/// A command, its exit code and what a preceding notice affects, and the closing line.
pub(super) struct ClosingStatusTestCase {
    pub(super) description: &'static str,
    pub(super) exit_code: Option<i64>,
    pub(super) affected: Option<&'static str>,
    pub(super) expected_status: &'static str,
}
