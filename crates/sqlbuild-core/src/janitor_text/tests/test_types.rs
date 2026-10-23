use crate::janitor_text::models::{
    JanitorItemText, JanitorOutcome, JanitorPhase, JanitorPlanText, JanitorResultCounts,
    JanitorRunText,
};

pub(super) struct ConfirmationTestCase {
    pub(super) description: &'static str,
    pub(super) plan: JanitorPlanText,
    pub(super) expected_prompt: &'static str,
}

pub(super) struct SettingsTestCase {
    pub(super) description: &'static str,
    pub(super) retention_days: i64,
    pub(super) history_versions: i64,
    pub(super) expected_code: Option<&'static str>,
}

pub(super) struct DisabledTestCase {
    pub(super) description: &'static str,
    pub(super) use_color: bool,
    pub(super) expected_text: &'static str,
}

pub(super) struct ItemLineTestCase {
    pub(super) description: &'static str,
    pub(super) position: (usize, usize),
    pub(super) item: JanitorItemText,
    pub(super) flow_width: usize,
    pub(super) expected_line: &'static str,
}

pub(super) struct PhaseTextTestCase {
    pub(super) description: &'static str,
    pub(super) phase: JanitorPhase,
    pub(super) items: Vec<JanitorItemText>,
    pub(super) total: usize,
    pub(super) elapsed_seconds: f64,
    pub(super) expected_start: &'static str,
    pub(super) expected_complete: &'static str,
    pub(super) expected_failed: &'static str,
}

pub(super) struct CompletionTestCase {
    pub(super) description: &'static str,
    pub(super) counts: JanitorResultCounts,
    pub(super) elapsed_seconds: Option<f64>,
    pub(super) failed: bool,
    pub(super) expected_text: &'static str,
}

pub(super) struct ItemCountsTestCase {
    pub(super) description: &'static str,
    pub(super) items: Vec<JanitorItemText>,
    pub(super) plan: JanitorPlanText,
    pub(super) expected_counts: JanitorResultCounts,
    pub(super) expected_archive_flow_width: usize,
}

pub(super) struct PreviewTestCase {
    pub(super) description: &'static str,
    pub(super) plan: JanitorPlanText,
    pub(super) verbose: bool,
    pub(super) expected_fragments: &'static [&'static str],
    pub(super) unexpected_fragments: &'static [&'static str],
}

pub(super) struct JsonTestCase {
    pub(super) description: &'static str,
    pub(super) plan: Option<JanitorPlanText>,
    pub(super) outcome: JanitorOutcome,
    pub(super) run: Option<JanitorRunText>,
    pub(super) error: Option<&'static str>,
    pub(super) expected_fragments: &'static [&'static str],
}

pub(super) struct EventsUnwrittenTestCase {
    pub(super) description: &'static str,
    pub(super) count: usize,
    pub(super) schemas: Vec<String>,
    pub(super) error: &'static str,
    pub(super) expected_text: &'static str,
}

pub(super) struct UsagePromptTestCase {
    pub(super) description: &'static str,
    pub(super) plan: JanitorPlanText,
    pub(super) expected_fragment: &'static str,
    pub(super) expected_phrase: &'static str,
}
