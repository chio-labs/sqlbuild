//! Planner change-detection inputs and results.

/// The replay a change asks for.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BackfillAction {
    Full,
    Bounded,
    ForwardOnly,
}

/// A backfill action with the duration of a bounded replay.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Backfill {
    pub action: BackfillAction,
    pub duration: Option<String>,
}

/// How a model changed since its recorded build, in precedence order.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChangeKind {
    QueryChanged,
    FunctionChanged,
    SchemaChanged,
    ConfigChanged,
    NoChange,
}

/// What a schema finding reports about one column.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SchemaChangeKind {
    ColumnAdded,
    ColumnRemoved,
    ColumnTypeChanged,
}

/// Where an expected column was declared.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SchemaColumnSource {
    Yml,
    SqlAnalysis,
}

/// One difference between expected and warehouse columns.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SchemaFindingRow {
    pub kind: SchemaChangeKind,
    pub column_name: String,
    pub source: SchemaColumnSource,
    pub expected_type: Option<String>,
    pub actual_type: Option<String>,
}

/// Expected and warehouse columns of one model: name and type.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SchemaColumns {
    pub yml: Vec<(String, String)>,
    pub inferred: Option<Vec<(String, Option<String>)>>,
    pub warehouse: Vec<(String, String)>,
}

/// How a model's columns are compared.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct SchemaComparison {
    pub type_enforcement: bool,
    pub inferred_schema_complete: bool,
    pub case_folding: bool,
}

/// The parts of version-identity metadata that changed since the recorded build.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct MetadataChanges {
    pub changed_functions: Vec<String>,
    pub config_changed: bool,
}

/// Facts the backfill of a detected change depends on.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct BackfillFacts {
    pub query_changed: bool,
    pub functions_changed: bool,
    pub config_changed: bool,
    pub declared_columns_changed: bool,
    pub schema_changed: bool,
}

/// One model rename a reference may have been rewritten for; `applies` when the recorded build predates it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RenameCandidate {
    pub new_name: String,
    pub origin_name: String,
    pub applies: bool,
}

/// A `__ref` name in the query: start and end character offsets and the name.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NameSpan {
    pub start: usize,
    pub end: usize,
    pub name: String,
}

/// Fingerprint metadata as version identity compares it: absent, undecodable text, or the decoded object.
#[derive(Clone, Debug, PartialEq)]
pub enum IdentityPayload {
    Absent,
    Raw(String),
    Object(serde_json::Map<String, serde_json::Value>),
}
