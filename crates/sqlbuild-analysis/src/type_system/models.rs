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

/// A Python `int` of any size, held as its canonical base-10 text.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PythonInteger(String);

impl PythonInteger {
    /// The integer whose sign and base-10 digits are given.
    #[must_use]
    pub fn from_digits(negative: bool, digits: &str) -> Self {
        let significant: &str = digits.trim_start_matches('0');
        if significant.is_empty() {
            return Self("0".to_owned());
        }
        Self(if negative {
            format!("-{significant}")
        } else {
            significant.to_owned()
        })
    }

    /// Whether the integer is zero, so Python treats it as false.
    #[must_use]
    pub fn is_zero(&self) -> bool {
        self.0 == "0"
    }

    /// The integer's canonical base-10 text, as Python's `str(value)` spells it.
    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl From<i64> for PythonInteger {
    fn from(value: i64) -> Self {
        Self(value.to_string())
    }
}

impl std::fmt::Display for PythonInteger {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

/// One type string's comparison shape.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NormalizedType {
    pub normalized_name: String,
    pub family: TypeFamily,
    pub precision: Option<PythonInteger>,
    pub scale: Option<PythonInteger>,
    pub length: Option<PythonInteger>,
}

/// Why Python's `normalize_type` raises instead of returning a type.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TypeNormalizationError {
    /// Polyglot does not know the dialect name: the wheel's `ValueError`.
    UnknownDialect(String),
    /// Polyglot cannot write the parsed type back as SQL: the wheel's `PolyglotError`.
    Generation(String),
}

impl TypeNormalizationError {
    /// The message Python's exception carries.
    #[must_use]
    pub fn message(&self) -> String {
        match self {
            Self::UnknownDialect(name) => format!("Unknown dialect: {name}"),
            Self::Generation(message) => message.clone(),
        }
    }
}

/// A normalized type and the Polyglot parse error Python logs before its text fallback.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TypeNormalization {
    pub normalized: NormalizedType,
    pub parse_error: Option<String>,
}
