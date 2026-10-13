//! Clone output labels.

use crate::clone_text::models::CloneStatusKind;

/// The width of the longest clone action value.
pub(crate) const ACTION_WIDTH: usize = "skipped_missing_dependency".len();
pub(crate) const FINGERPRINT_LABEL: &str = "fingerprint";
pub(crate) const FINGERPRINT_LABEL_WIDTH: usize = 10;
pub(crate) const PENDING_IDENTITY_LIMIT: usize = 10;

/// Action footer labels and the action value each counts.
pub(crate) const ACTION_SUMMARY: [(&str, &str); 4] = [
    ("CLONED", "cloned"),
    ("COPIED", "copied"),
    ("RECREATED_VIEWS", "recreated_view"),
    ("RECREATED_FUNCTIONS", "recreated_function"),
];

/// Status footer labels and the status each counts.
pub(crate) const STATUS_SUMMARY: [(&str, CloneStatusKind); 3] = [
    ("PASS", CloneStatusKind::Success),
    ("WARN", CloneStatusKind::Warning),
    ("FAIL", CloneStatusKind::Failed),
];
