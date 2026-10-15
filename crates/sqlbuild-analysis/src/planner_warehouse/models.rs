//! Values exchanged with warehouse-inspection planning.

/// One logical cursor bound wanted from a physical relation column.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CursorTagRequest {
    pub relation: String,
    pub cursor_column: String,
    pub cursor_type: Option<String>,
    pub min_tag: Option<String>,
    pub max_tag: String,
}

/// One physical relation and cursor column read once for every logical bound it serves.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PhysicalCursorQuery {
    pub relation: String,
    pub cursor_column: String,
    pub cursor_type: String,
    pub min_tags: Vec<String>,
    pub max_tags: Vec<String>,
}

/// A selected external source table the warehouse did not list and could not read.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MissingSourceTable {
    pub source_name: String,
    pub relation: String,
    pub read_by: Vec<String>,
    pub unreadable: bool,
    pub role: Option<String>,
    pub location: String,
}

/// The change facts that explain an incremental full rebuild.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct FullRebuildFacts {
    pub full_refresh: bool,
    pub change_kind: String,
    pub query_changed: bool,
    pub changed_functions: Vec<String>,
    pub has_schema_findings: bool,
}

/// The key parts of one migration fingerprint cache entry.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FingerprintCacheKey {
    pub shared_digest: String,
    pub query_sql: String,
    pub metadata_json: String,
    pub dialect: Option<String>,
    pub visible_renames: Vec<(String, String)>,
}
