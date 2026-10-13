//! Freshness output labels and glyphs.

use crate::freshness_text::models::FreshnessStatus;

pub(crate) const TREE_BRANCH_GLYPH: &str = "\u{251c}\u{2500}\u{2500}";
pub(crate) const TREE_LAST_GLYPH: &str = "\u{2514}\u{2500}\u{2500}";

/// Status groups in output order, with their titles.
pub(crate) const GROUPS: [(FreshnessStatus, &str); 6] = [
    (FreshnessStatus::Observed, "Observed"),
    (FreshnessStatus::Changed, "Changed"),
    (FreshnessStatus::Unchanged, "Unchanged"),
    (FreshnessStatus::Tolerated, "Tolerated"),
    (FreshnessStatus::Unknown, "Unknown"),
    (FreshnessStatus::Error, "Errors"),
];

/// Status footer labels, their JSON keys, and the status each counts.
pub(crate) const STATUS_SUMMARY: [(&str, &str, FreshnessStatus); 6] = [
    ("OBSERVED", "observed", FreshnessStatus::Observed),
    ("CHANGED", "changed", FreshnessStatus::Changed),
    ("UNCHANGED", "unchanged", FreshnessStatus::Unchanged),
    ("TOLERATED", "tolerated", FreshnessStatus::Tolerated),
    ("UNKNOWN", "unknown", FreshnessStatus::Unknown),
    ("ERROR", "errors", FreshnessStatus::Error),
];

/// Age footer labels, their JSON keys, and the age status each counts.
pub(crate) const AGE_SUMMARY: [(&str, &str, &str); 4] = [
    ("PASS", "age_pass", "pass"),
    ("WARN", "age_warn", "warn"),
    ("ERROR", "age_error", "error"),
    ("UNKNOWN", "age_unknown", "unknown"),
];
