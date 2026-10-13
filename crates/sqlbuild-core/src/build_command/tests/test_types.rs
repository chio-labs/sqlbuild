use crate::build_command::models::{
    Confirmation, DurationLimit, PhaseTimings, PlanSafetyFacts, PlanSafetyGates, PythonNodeRow,
    RunContextFacts,
};

pub(super) struct PolicyTestCase {
    pub(super) description: &'static str,
    pub(super) facts: PlanSafetyFacts,
    pub(super) gates: PlanSafetyGates,
    pub(super) max_models: Option<i64>,
    /// `refuse:<code>:<message>` or `confirm:<expected>:<refusal message>:<cancellation message>`.
    pub(super) expected_steps: Vec<String>,
}

pub(super) struct DurationTestCase {
    pub(super) description: &'static str,
    pub(super) limit: DurationLimit,
    pub(super) expected_error: Option<(&'static str, &'static str)>,
}

pub(super) struct TimingsTestCase {
    pub(super) description: &'static str,
    pub(super) timings: PhaseTimings,
    pub(super) expected_text: &'static str,
}

pub(super) struct ContextTestCase {
    pub(super) description: &'static str,
    pub(super) facts: RunContextFacts,
    pub(super) expected_text: &'static str,
}

pub(super) struct PythonRowsTestCase {
    pub(super) description: &'static str,
    pub(super) rows: Vec<PythonNodeRow>,
    pub(super) expected_failed: bool,
    pub(super) expected_text: &'static str,
}

pub(super) struct ExitCodeTestCase {
    pub(super) description: &'static str,
    pub(super) outcome: (bool, bool, bool),
    pub(super) expected_exit_code: i32,
}

pub(super) struct PromptTestCase {
    pub(super) description: &'static str,
    pub(super) confirmation: Confirmation,
    pub(super) expected_text: &'static str,
}
