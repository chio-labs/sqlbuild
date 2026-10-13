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
    pub fn label(self, text: &str) -> String {
        self.apply(DIM, text)
    }

    #[must_use]
    pub fn accent(self, text: &str) -> String {
        self.apply(BLUE, text)
    }

    #[must_use]
    pub fn plan_section(self, text: &str) -> String {
        self.apply(BOLD, text)
    }

    #[must_use]
    pub fn warning_strong(self, text: &str) -> String {
        self.apply(&format!("{YELLOW}{BOLD}"), text)
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

/// How many entries each bounded section of human output shows.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DisplayLimit {
    /// `None` shows every entry.
    pub max_entries: Option<usize>,
    /// The flag the overflow line suggests, such as `--verbose`.
    pub overflow_flag: String,
}

/// The cursor detail of one planned model, with the planner's display text already rendered.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CursorPlanText {
    pub column: String,
    pub cursor_type: Option<String>,
    pub microbatch: bool,
    pub requested_start: Option<String>,
    pub requested_end: Option<String>,
    /// The planner's no-input-rows or waiting text, when inputs are empty.
    pub empty_inputs_window: Option<String>,
    pub waiting_on_empty_inputs: bool,
    /// `start → inclusive end`, when the bounds are resolved.
    pub range: Option<String>,
    pub declared_grain: Option<String>,
    pub effective_grain: Option<String>,
    pub declared_batch_size: Option<String>,
    pub effective_batch_size: Option<String>,
    pub planned_batch_count: Option<i64>,
    /// The runtime resolves the bounds.
    pub runtime_owned: bool,
    /// Resolution status `resolved` or `deferred`; anything else is neither.
    pub resolved: bool,
    pub deferred: bool,
    /// `once ... is up to date`, naming the runtime-owned cursor inputs.
    pub runtime_inputs_clause: String,
    /// `str(entry.batch_concurrency)`.
    pub batch_concurrency: String,
    pub unaccounted_partition_policy: Option<String>,
}

/// One schema finding of a planned model: `column_added`, `column_removed` or `column_type_changed`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SchemaFindingText {
    pub kind: String,
    pub column_name: String,
    pub expected_type: Option<String>,
    pub actual_type: Option<String>,
}

/// A hint that an added column may be a rename.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RenameHintText {
    pub added_column: String,
    pub message: String,
}

/// One planned model as the text plan shows it.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ModelPlanText {
    pub name: String,
    /// `PlanAction` value.
    pub action: String,
    /// `PlanReason` value.
    pub reason: String,
    pub materialization_label: String,
    pub custom_materialization_name: Option<String>,
    /// `BackfillAction` value.
    pub backfill_action: String,
    pub backfill_duration: Option<String>,
    pub cursor: Option<CursorPlanText>,
    pub changed_functions: Vec<String>,
    pub schema_findings: Vec<SchemaFindingText>,
    pub rename_hints: Vec<RenameHintText>,
    /// The rendered config diff, when the version config changed.
    pub config_diff: Option<Vec<String>>,
    /// The rendered query diff, when the query changed and the previous query is known.
    pub query_diff: Option<Vec<String>>,
}

/// One planned function.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FunctionPlanText {
    pub name: String,
    pub reason: String,
    /// `table function` or `<language> udf`.
    pub kind: String,
    /// The rendered query diff, when the query changed and the previous query is known.
    pub query_diff: Option<Vec<String>>,
}

/// One planned seed.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SeedPlanText {
    pub name: String,
    pub reason: String,
}

/// One planned source or loader load.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SourceLoadPlanText {
    pub name: String,
    /// `ExecutionResourceKind` value; only `loader` and `source` loads are listed.
    pub resource_kind: String,
    pub is_reload: bool,
    pub integration_kind: Option<String>,
    pub write_strategy: Option<String>,
    pub cursor_column: Option<String>,
    pub unique_key: Vec<String>,
}

/// One planned Python node, with its rendered identity diffs.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PythonPlanText {
    pub name: String,
    pub kind: String,
    /// `pre_sql_ingress` or `read_side`.
    pub phase: String,
    pub identity_status: String,
    pub source_diff: Vec<String>,
    pub dependency_diff: Vec<String>,
}

/// One provider used by a selected Python surface.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProviderUsageText {
    pub provider_name: String,
    pub consumer_kind: String,
    pub consumer_name: String,
    pub parameter_name: String,
    pub annotation_class_name: Option<String>,
}

/// One plan warning.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PlanWarningText {
    /// `error`, `warning` or `info`.
    pub severity: String,
    pub message: String,
    pub model_name: Option<String>,
}

/// The source freshness observed by a direct plan, by outcome.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SourceFreshnessText {
    pub observed: Vec<String>,
    pub changed: Vec<String>,
    pub unchanged: Vec<String>,
    pub unknown: Vec<String>,
    pub age_warnings: Vec<String>,
    pub age_errors: Vec<String>,
    pub stale_models: Vec<String>,
    pub blocked_models: Vec<String>,
}

/// Everything the text plan renders.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PlanTextReport {
    pub use_color: bool,
    pub include_header: bool,
    /// The plan was requested with `--full-refresh`.
    pub full_refresh: bool,
    pub display: DisplayLimit,
    pub include_freshness_diagnostics: bool,
    /// The plan's explicit selection-diagnostics policy, when it sets one.
    pub selection_diagnostics: Option<bool>,
    pub models: Vec<ModelPlanText>,
    pub functions: Vec<FunctionPlanText>,
    pub seeds: Vec<SeedPlanText>,
    pub source_loads: Vec<SourceLoadPlanText>,
    pub python_entries: Vec<PythonPlanText>,
    /// The plan's provider usages, then each Python entry's.
    pub provider_usages: Vec<ProviderUsageText>,
    pub warnings: Vec<PlanWarningText>,
    pub source_freshness: Option<SourceFreshnessText>,
    pub remaining_stale_models: Vec<String>,
    pub pruned_models: Vec<String>,
    /// Table type, retention and migration lines the planner renders.
    pub pre_build_lines: Vec<String>,
}

/// The structural kind of a rendered plan line.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum RowKind {
    Entry,
    Leaf,
    Nested,
    Other,
}
