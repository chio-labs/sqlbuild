//! Display facts of a janitor plan and its execution, read from the executor's models.

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
    /// Direct state tables to prune and the versions each keeps.
    pub state_prunes: Vec<(String, i64)>,
    /// Skipped relations and why.
    pub skipped_relations: Vec<(String, String)>,
    pub skipped_schemas: Vec<SourceSchemaText>,
    pub blocked_schemas: Vec<SourceSchemaText>,
}

/// How many items one janitor run changed.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct JanitorResultCounts {
    pub archived: usize,
    pub deleted: usize,
    pub deleted_archives: usize,
    pub deleted_query_artifacts: usize,
    pub dropped_old_name_views: usize,
    pub pruned_direct_state: usize,
}
