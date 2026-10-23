//! Display facts of a janitor plan and its execution, read from the executor's models.

/// Reads of one relation within the usage window.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct RelationUsageText {
    /// The latest read as `YYYY-MM-DD HH:MM:SS` UTC.
    pub last_read_at: String,
    /// Reader user names, most queries first.
    pub readers: Vec<String>,
    pub query_count: i64,
    /// The objects it was read through when it was never read directly; empty when unnamed.
    pub via: Option<Vec<String>>,
}

/// A relation to archive: its name, archive name, age and expiry.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ArchiveCandidateText {
    pub name: String,
    pub archive_name: String,
    /// Whole days old at planning time, or none when unknown.
    pub age_days: Option<i64>,
    /// Whether the archive expires no later than it is created.
    pub expires_now: bool,
    /// The expiry as `YYYY-MM-DD HH:MM:SS`.
    pub expires_at: String,
    /// Whether the relation is a table, whose data stops changing once it is stale.
    pub is_table: bool,
    /// The date it last changed as `YYYY-MM-DD`, or none when unknown.
    pub changed_on: Option<String>,
    /// Its reads within the usage window, or none when unread or not checked.
    pub usage: Option<RelationUsageText>,
}

/// Whether the janitor checked reads of its archive candidates.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct UsageCheckText {
    pub checked: bool,
    /// Why usage was not checked.
    pub reason: Option<String>,
    /// The usage window as configured, such as `7d`.
    pub window: String,
    /// Whether in-use relations are kept instead of archived.
    pub keep_in_use: bool,
    /// What a check that ran could not cover, such as view chains it could not follow.
    pub notices: Vec<String>,
}

/// An archived relation to delete or retain.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ArchivedRelationText {
    pub name: String,
    /// Whether this run archives it.
    pub archived_in_run: bool,
    /// The archive time as `YYYY-MM-DD HH:MM:SS`.
    pub archived_at: String,
    pub age_days: Option<i64>,
    pub expires_at: String,
}

/// A compatibility view at a model's old name.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct OldNameViewText {
    pub name: String,
    pub destination_model: String,
    /// The expiry as `YYYY-MM-DD`, or none.
    pub expires_on: Option<String>,
    pub drop_reason: Option<String>,
    pub occupied: bool,
    pub claimed_by: Option<String>,
}

/// A schema skipped or blocked by active sources.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SourceSchemaText {
    pub name: String,
    pub source_names: Vec<String>,
    pub suppressed_candidates: Vec<String>,
    pub suppressed_archive_deletions: Vec<String>,
}

/// One janitor plan as its preview, confirmation and work check read it.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct JanitorPlanText {
    pub target_name: Option<String>,
    pub retention_days: i64,
    pub direct_mode: bool,
    pub archive_retention_days: i64,
    pub age_metadata_supported: bool,
    pub scanned_schema_count: i64,
    pub candidates: Vec<String>,
    pub archive_candidates: Vec<ArchiveCandidateText>,
    pub archive_deletions: Vec<ArchivedRelationText>,
    pub retained_archives: Vec<ArchivedRelationText>,
    pub old_name_drops: Vec<OldNameViewText>,
    pub old_name_live: Vec<OldNameViewText>,
    pub old_name_missing: Vec<OldNameViewText>,
    pub query_artifacts: Vec<String>,
    /// Leftover review schemas to drop.
    pub review_schemas: Vec<String>,
    /// Direct state tables to prune and the versions each keeps.
    pub state_prunes: Vec<(String, i64)>,
    /// Skipped relations and why.
    pub skipped_relations: Vec<(String, String)>,
    pub skipped_schemas: Vec<SourceSchemaText>,
    pub blocked_schemas: Vec<SourceSchemaText>,
    /// The usage check of the archive candidates, or none when it did not run.
    pub usage_check: Option<UsageCheckText>,
    /// In-use relations kept instead of archived.
    pub kept_in_use: Vec<ArchiveCandidateText>,
}

/// How many items one janitor run changed.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct JanitorResultCounts {
    pub archived: usize,
    pub deleted: usize,
    pub deleted_archives: usize,
    pub deleted_query_artifacts: usize,
    pub dropped_review_schemas: usize,
    pub dropped_old_name_views: usize,
    pub pruned_direct_state: usize,
}

/// One janitor apply phase, in execution order.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum JanitorPhase {
    DeleteRelations,
    Archive,
    DeleteArchives,
    DropOldNameViews,
    DropQueryArtifacts,
    DropReviewSchemas,
    PruneDirectState,
}

impl JanitorPhase {
    /// The phase from the executor's `JanitorPhase` value.
    #[must_use]
    pub fn from_value(value: &str) -> Option<Self> {
        match value {
            "delete_relations" => Some(Self::DeleteRelations),
            "archive" => Some(Self::Archive),
            "delete_archives" => Some(Self::DeleteArchives),
            "drop_old_name_views" => Some(Self::DropOldNameViews),
            "drop_query_artifacts" => Some(Self::DropQueryArtifacts),
            "drop_review_schemas" => Some(Self::DropReviewSchemas),
            "prune_direct_state" => Some(Self::PruneDirectState),
            _ => None,
        }
    }

    /// The executor's `JanitorPhase` value.
    #[must_use]
    pub fn value(self) -> &'static str {
        match self {
            Self::DeleteRelations => "delete_relations",
            Self::Archive => "archive",
            Self::DeleteArchives => "delete_archives",
            Self::DropOldNameViews => "drop_old_name_views",
            Self::DropQueryArtifacts => "drop_query_artifacts",
            Self::DropReviewSchemas => "drop_review_schemas",
            Self::PruneDirectState => "prune_direct_state",
        }
    }
}

/// One finished janitor action.
#[derive(Clone, Debug, PartialEq)]
pub struct JanitorItemText {
    pub phase: JanitorPhase,
    /// The `JanitorAction` value, such as `archived`.
    pub action: String,
    pub name: String,
    /// Where the action moved the relation, such as its archive name.
    pub destination: Option<String>,
    /// The error that stopped the action, or none when it succeeded.
    pub error: Option<String>,
    pub duration_seconds: Option<f64>,
}

/// The actions a janitor run finished, what it changed, and how long it took.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct JanitorRunText {
    pub items: Vec<JanitorItemText>,
    pub counts: JanitorResultCounts,
    pub elapsed_seconds: f64,
}

/// How a janitor invocation ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum JanitorOutcome {
    /// Janitor is not enabled for the project.
    Disabled,
    /// An inspection-only `--as` preview.
    Previewed,
    /// Active sources block every action.
    Blocked,
    /// The plan changes nothing.
    NothingToDo,
    Cancelled,
    Completed,
    /// An action failed after the cleanup started.
    Failed,
}

impl JanitorOutcome {
    /// The `status` of `sqb janitor --json`.
    #[must_use]
    pub fn value(self) -> &'static str {
        match self {
            Self::Disabled => "disabled",
            Self::Previewed => "previewed",
            Self::Blocked => "blocked",
            Self::NothingToDo => "nothing_to_do",
            Self::Cancelled => "cancelled",
            Self::Completed => "completed",
            Self::Failed => "failed",
        }
    }
}
