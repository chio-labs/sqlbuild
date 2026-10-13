//! Plain data of the human compile report, and the semantic styling it is rendered with.

use crate::cli_text::constants::{
    BLUE, BOLD, DIM, ERROR_STATUS_LABELS, GREEN, RED, RESET, SKIPPED_STATUS_LABELS,
    SUCCESS_STATUS_LABELS, WARNING_STATUS_LABELS, YELLOW,
};

/// The default CLI theme, applied only when color is enabled.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CliStyle {
    pub use_color: bool,
}

impl CliStyle {
    /// `TextStyle.apply`: the text wrapped in `prefix` and a reset, unless color or text is off.
    fn apply(self, prefix: &str, text: &str) -> String {
        if !self.use_color || prefix.is_empty() || text.is_empty() {
            return text.to_owned();
        }
        format!("{prefix}{text}{RESET}")
    }

    #[must_use]
    pub fn title(self, text: &str) -> String {
        self.apply(&format!("{BLUE}{BOLD}"), text)
    }

    #[must_use]
    pub fn muted(self, text: &str) -> String {
        self.apply(DIM, text)
    }

    #[must_use]
    pub fn object_name(self, text: &str) -> String {
        self.apply("", text)
    }

    #[must_use]
    pub fn success(self, text: &str) -> String {
        self.apply(GREEN, text)
    }

    #[must_use]
    pub fn warning(self, text: &str) -> String {
        self.apply(YELLOW, text)
    }

    #[must_use]
    pub fn error(self, text: &str) -> String {
        self.apply(RED, text)
    }

    #[must_use]
    pub fn error_strong(self, text: &str) -> String {
        self.apply(&format!("{RED}{BOLD}"), text)
    }

    /// `CliStyle.status`: the status word styled by what it reports.
    #[must_use]
    pub fn status(self, status: &str) -> String {
        let normalized: String = status.to_uppercase();
        if SUCCESS_STATUS_LABELS.contains(&normalized.as_str()) {
            return self.success(status);
        }
        if WARNING_STATUS_LABELS.contains(&normalized.as_str()) {
            return self.warning(status);
        }
        if ERROR_STATUS_LABELS.contains(&normalized.as_str()) {
            return self.error(status);
        }
        if SKIPPED_STATUS_LABELS.contains(&normalized.as_str()) {
            return self.muted(status);
        }
        status.to_owned()
    }
}

/// One source location, with the authored text of its file when the report has it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LocationText {
    /// `str(location.path)`.
    pub path: String,
    pub line: i64,
    pub column: i64,
    pub end_line: Option<i64>,
    pub end_column: Option<i64>,
    /// The authored text of `path`, when the report holds it.
    pub source: Option<String>,
}

/// A related location of a diagnostic: its label, location and optional caret message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RelatedText {
    pub label: String,
    pub location: LocationText,
    pub message: Option<String>,
}

/// One diagnostic as the human report renders it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DiagnosticText {
    /// `str(diagnostic.severity)`: `error`, `warning` or `info`.
    pub severity: String,
    pub code: String,
    pub message: String,
    /// `str(diagnostic.resource_type)`, when set.
    pub resource_type: Option<String>,
    pub resource_name: Option<String>,
    pub location: Option<LocationText>,
    /// `str(diagnostic.path)`, shown only when there is no location.
    pub path: Option<String>,
    pub related: Vec<RelatedText>,
    pub notes: Vec<String>,
    pub affected_rules: Vec<String>,
    pub help: Option<String>,
    /// How many equal warnings this one stands for; errors and notes are always `1`.
    pub occurrences: usize,
}

/// What the human report says about column lineage.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LineageNote {
    /// Rich lineage completed.
    Rich,
    /// Lineage was expected but is missing.
    Unavailable,
    /// Nothing to say.
    Silent,
}

/// One listed model: its name, whether an error names it, and its output column count.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ModelLine {
    pub name: String,
    pub failed: bool,
    pub column_count: i64,
}

/// Everything the human compile report renders.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CompileTextReport {
    pub style: CliStyle,
    /// Every selected model, in project order.
    pub models: Vec<ModelLine>,
    pub semantic_notice: Option<String>,
    /// The diagnostics shown, with repeated equal warnings already folded.
    pub diagnostics: Vec<DiagnosticText>,
    pub seed_count: usize,
    pub function_count: usize,
    pub error_count: usize,
    pub warning_count: usize,
    /// The compiled SQL directory relative to `target/`'s parent, without a trailing slash.
    pub compiled_dir: String,
    pub manifest: bool,
    pub lineage: LineageNote,
}
