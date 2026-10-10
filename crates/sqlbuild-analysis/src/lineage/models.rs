//! Plain-data request and outcomes for fast column lineage.

/// The SQLBuild resource kinds a `__ref`, `__source` or `__seed` call names.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LineageResourceType {
    Model,
    Source,
    Seed,
}

impl LineageResourceType {
    /// Python's `CompiledResourceType` value.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Model => "model",
            Self::Source => "source",
            Self::Seed => "seed",
        }
    }

    /// Parse Python's `CompiledResourceType` value for the kinds lineage reads.
    pub fn from_value(value: &str) -> Option<Self> {
        match value {
            "model" => Some(Self::Model),
            "source" => Some(Self::Source),
            "seed" => Some(Self::Seed),
            _ => None,
        }
    }
}

/// Python's `ColumnTransformKind` values that fast lineage produces.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineageTransformKind {
    Direct,
    Cast,
    Expression,
    Aggregation,
    Star,
    Constant,
}

impl LineageTransformKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Direct => "direct",
            Self::Cast => "cast",
            Self::Expression => "expression",
            Self::Aggregation => "aggregation",
            Self::Star => "star",
            Self::Constant => "constant",
        }
    }
}

/// Python's `ColumnLineageConfidence` values that fast lineage produces.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineageConfidence {
    High,
    Medium,
    Unknown,
}

impl LineageConfidence {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::High => "high",
            Self::Medium => "medium",
            Self::Unknown => "unknown",
        }
    }
}

/// One resource's known columns, in the order Python's schema mapping lists them.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LineageSchemaResource {
    pub resource_type: LineageResourceType,
    pub name: String,
    /// Inferred then declared column names; repeats keep their first position.
    pub columns: Vec<String>,
}

/// The work one model needs: star expansion over compact facts, or a parse of its SQL.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FastLineageModel {
    /// A model with compact facts and an unresolved root star.
    StarExpansion {
        query_sql: String,
        existing_columns: Vec<String>,
    },
    /// A model without compact facts.
    Parse {
        query_sql: String,
        inferred_columns: Vec<String>,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FastLineageRequest {
    /// The adapter's analysis dialect; `None` parses as generic SQL.
    pub dialect: Option<String>,
    pub schema: Vec<LineageSchemaResource>,
    pub models: Vec<FastLineageModel>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LineageSource {
    pub resource_type: LineageResourceType,
    pub resource_name: String,
    pub column_name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LineageColumn {
    pub output_column: String,
    pub transform_kind: LineageTransformKind,
    pub confidence: LineageConfidence,
    pub upstream_columns: Vec<LineageSource>,
}

/// Why a model is handed back to Python, which builds its lineage exactly as before.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineageDeferral {
    /// The dialect is not compiled into the native parser.
    UnsupportedDialect,
    /// The parsed SQL could not be read as Python reads it.
    NativeFailure,
}

impl LineageDeferral {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::UnsupportedDialect => "unsupported_dialect",
            Self::NativeFailure => "native_failure",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FastLineageOutcome {
    /// Star columns to append to the model's compact facts.
    StarColumns(Vec<LineageColumn>),
    /// Lineage built from the parsed SQL.
    Built {
        columns: Vec<LineageColumn>,
        has_star: bool,
    },
    /// Python records no lineage for this model.
    Omitted,
    /// The SQL did not parse; Python logs this message and records no lineage.
    Unparsed(String),
    Deferred(LineageDeferral),
}

impl FastLineageOutcome {
    /// `(status, columns, has_star, detail)`: detail is the parse error or the deferral kind.
    pub fn into_parts(self) -> (&'static str, Vec<LineageColumn>, bool, Option<String>) {
        match self {
            Self::StarColumns(columns) => ("star", columns, true, None),
            Self::Built { columns, has_star } => ("built", columns, has_star, None),
            Self::Omitted => ("omitted", Vec::new(), false, None),
            Self::Unparsed(message) => ("unparsed", Vec::new(), false, Some(message)),
            Self::Deferred(kind) => (
                "deferred",
                Vec::new(),
                false,
                Some(kind.as_str().to_owned()),
            ),
        }
    }
}

/// Python's `InferredNullability` values that rich lineage produces.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineageNullability {
    NonNull,
    Nullable,
    Unknown,
}

impl LineageNullability {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::NonNull => "non_null",
            Self::Nullable => "nullable",
            Self::Unknown => "unknown",
        }
    }
}

/// One resource's typed columns, as Python's schema mapping builds them.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RichSchemaResource {
    pub resource_type: LineageResourceType,
    pub name: String,
    /// `columns[name] = type or "UNKNOWN"`: a repeat keeps its position and takes the later type.
    pub assigned: Vec<(String, Option<String>)>,
    /// `columns.setdefault(name, type or "UNKNOWN")`, applied after `assigned`.
    pub defaulted: Vec<(String, Option<String>)>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RichLineageRequest {
    /// The `PolyglotAnalysisDialect` value Python resolved from the adapter's dialect.
    pub dialect: String,
    pub schema: Vec<RichSchemaResource>,
    /// Each requested model's compiled query SQL, in project order.
    pub models: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RichLineageColumn {
    pub column: LineageColumn,
    pub nullability: LineageNullability,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RichLineageOutcome {
    Built {
        columns: Vec<RichLineageColumn>,
        has_star: bool,
    },
    /// Polyglot rejected the query; Python logs this message and records no lineage.
    Skipped(String),
    /// Only `UnsupportedDialect`: the wheel answers dialects this build lacks.
    Deferred(LineageDeferral),
}

impl RichLineageOutcome {
    /// `(status, columns, has_star, detail)`: detail is the polyglot error or the deferral kind.
    pub fn into_parts(self) -> (&'static str, Vec<RichLineageColumn>, bool, Option<String>) {
        match self {
            Self::Built { columns, has_star } => ("built", columns, has_star, None),
            Self::Skipped(message) => ("skipped", Vec::new(), false, Some(message)),
            Self::Deferred(kind) => (
                "deferred",
                Vec::new(),
                false,
                Some(kind.as_str().to_owned()),
            ),
        }
    }
}

/// What a directory whose `readdir` fails mid-listing does to the fingerprint, by Python version.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InterruptedListingPolicy {
    /// Python 3.12: `Path.walk` lets the `OSError` escape `rglob`, so the result is `None`.
    Uncacheable,
    /// Python 3.13 and 3.14: `glob` skips the directory's entries.
    Skip,
}

/// The relation lineage cache key Python's `relation_lineage_fingerprint` computes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RelationFingerprint {
    /// The hex SHA-256 digest of the authored inputs.
    Digest(String),
    /// Python returns `None`: dynamic context, malformed environment markers or unreadable input.
    Uncacheable,
    /// Discovery's snapshot could not be read (its walk reports no such failure today).
    Deferred,
}

impl RelationFingerprint {
    /// `(status, digest)`.
    pub fn into_parts(self) -> (&'static str, Option<String>) {
        match self {
            Self::Digest(digest) => ("digest", Some(digest)),
            Self::Uncacheable => ("uncacheable", None),
            Self::Deferred => ("deferred", None),
        }
    }
}
