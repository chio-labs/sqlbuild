//! Normalized type shapes, matching Python's `NormalizedType` and `TypeFamily`.

/// The semantic family of one normalized type.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TypeFamily {
    Integer,
    Decimal,
    Float,
    String,
    Boolean,
    Timestamp,
    Date,
    Datetime,
    Other,
}

impl TypeFamily {
    /// The value of Python's `TypeFamily` member.
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Integer => "integer",
            Self::Decimal => "decimal",
            Self::Float => "float",
            Self::String => "string",
            Self::Boolean => "boolean",
            Self::Timestamp => "timestamp",
            Self::Date => "date",
            Self::Datetime => "datetime",
            Self::Other => "other",
        }
    }
}

/// The dialects Python's type normalization distinguishes (`TypeDialect`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TypeDialect {
    Generic,
    BigQuery,
    Snowflake,
    DuckDb,
    MotherDuck,
    Databricks,
    Postgres,
    Tsql,
}

/// One type string's comparison shape.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NormalizedType {
    pub normalized_name: String,
    pub family: TypeFamily,
    pub precision: Option<i64>,
    pub scale: Option<i64>,
    pub length: Option<i64>,
}

/// A normalized type and the Polyglot parse error Python logs before its text fallback.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TypeNormalization {
    pub normalized: NormalizedType,
    pub parse_error: Option<String>,
}
