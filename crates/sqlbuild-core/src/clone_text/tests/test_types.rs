use crate::clone_text::models::{CloneItemText, FingerprintProgress};

pub(super) struct DisplayNameTestCase {
    pub(super) description: &'static str,
    pub(super) relation: &'static str,
    pub(super) expected_name: &'static str,
}

pub(super) struct ItemLineTestCase {
    pub(super) description: &'static str,
    pub(super) position: (usize, usize),
    pub(super) item: CloneItemText,
    pub(super) relation_width: usize,
    pub(super) use_color: bool,
    pub(super) expected_line: &'static str,
}

pub(super) struct CompletionTestCase {
    pub(super) description: &'static str,
    pub(super) items: Vec<CloneItemText>,
    pub(super) elapsed_seconds: Option<f64>,
    pub(super) use_color: bool,
    pub(super) expected_text: &'static str,
    pub(super) expected_exit_code: i32,
}

pub(super) struct FingerprintTestCase {
    pub(super) description: &'static str,
    pub(super) progress: FingerprintProgress,
    pub(super) expected_progress_line: &'static str,
    pub(super) expected_interrupted_line: Option<&'static str>,
}

pub(super) struct TargetTestCase {
    pub(super) description: &'static str,
    pub(super) targets: (&'static str, &'static str),
    pub(super) policy: (bool, bool),
    pub(super) expected_codes: (Option<&'static str>, Option<&'static str>),
}
