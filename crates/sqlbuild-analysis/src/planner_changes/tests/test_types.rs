use crate::planner_changes::models::{
    Backfill, BackfillFacts, ChangeKind, SchemaColumns, SchemaComparison, SchemaFindingRow,
};

pub(super) struct ReplayTestCase {
    pub(super) description: &'static str,
    pub(super) raw: Option<&'static str>,
    pub(super) expected_backfill: Result<Backfill, String>,
}

pub(super) struct MetadataTextTestCase {
    pub(super) description: &'static str,
    pub(super) metadata_json: &'static str,
    pub(super) expected_with_hash: &'static str,
    pub(super) expected_without_hash: &'static str,
    pub(super) expected_recorded_hash: Option<&'static str>,
}

pub(super) struct MetadataChangesTestCase {
    pub(super) description: &'static str,
    pub(super) current: &'static str,
    pub(super) recorded: Option<&'static str>,
    pub(super) origin_names: Option<Vec<(String, String)>>,
    pub(super) expected_functions: Vec<String>,
    pub(super) expected_config_changed: bool,
}

pub(super) struct DecisionTestCase {
    pub(super) description: &'static str,
    pub(super) facts: BackfillFacts,
    pub(super) replay_on_change: Option<&'static str>,
    pub(super) expected_kind: ChangeKind,
    pub(super) expected_backfill: Backfill,
}

pub(super) struct SchemaTestCase {
    pub(super) description: &'static str,
    pub(super) columns: SchemaColumns,
    pub(super) comparison: SchemaComparison,
    pub(super) expected_findings: Vec<SchemaFindingRow>,
}

pub(super) struct OriginTestCase {
    pub(super) description: &'static str,
    pub(super) query_sql: &'static str,
    pub(super) recorded_query: &'static str,
    pub(super) renames: Vec<(&'static str, &'static str, bool)>,
    pub(super) span_names: Vec<&'static str>,
    pub(super) expected_mapping: Option<Vec<(String, String)>>,
}
