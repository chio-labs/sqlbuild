//! What the model validators read besides the effective config values.

use std::collections::HashSet;

use crate::errors::ConfigError;

/// Project-wide facts every model's validation reads.
#[derive(Clone, Debug, Default)]
pub struct ProjectValidationFacts {
    /// Discovered custom materialization names.
    pub custom_materializations: HashSet<String>,
    /// Whether the project enables concurrent microbatches.
    pub microbatch_concurrency: bool,
    /// Discovered model names.
    pub models: HashSet<String>,
    /// Discovered seed names.
    pub seeds: HashSet<String>,
    /// Discovered source names.
    pub sources: HashSet<String>,
    /// Discovered SQL function names, scalar and table.
    pub functions: HashSet<String>,
    /// Discovered table function names.
    pub table_functions: HashSet<String>,
}

/// One extracted SQL reference: its `SqlReferenceKind` value and name.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ModelReference {
    pub kind: String,
    pub name: String,
}

/// One model's facts beyond its config values.
#[derive(Clone, Debug)]
pub struct ModelValidationFacts<'a> {
    pub model_name: &'a str,
    /// The model file's project-relative path, as reference errors name it.
    pub relative_path: &'a str,
    /// Merged references in extraction order.
    pub references: &'a [ModelReference],
    /// Column names of the model's declared schema, when one applies.
    pub declared_columns: Option<&'a [String]>,
    /// The expanded query SQL.
    pub query_sql: &'a str,
    /// Whether the resolved time-travel retention is unmanaged.
    pub retention_unmanaged: bool,
    /// Whether the resolved table type was declared by any layer.
    pub table_type_declared: bool,
}

/// Why native validation cannot decide a value: Python must run and decide.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rejected;

/// Why native validation stops: Python must decide, or the exact error the validators raise.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ValidationStop {
    /// The config holds a value only Python can judge; the Python validators run.
    Defer,
    /// The first error the Python validators raise.
    Error(ConfigError),
}

impl From<Rejected> for ValidationStop {
    fn from(_: Rejected) -> Self {
        Self::Defer
    }
}

/// The header's `time_travel_retention`, applied over the inherited policy.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RetentionOverride {
    /// Absent or `inherit`: keep the inherited policy.
    Inherit,
    /// `disabled`: retention is unmanaged.
    Unmanaged,
    /// A whole-day duration, or `0d`.
    Days(u64),
}

/// The header's `table_type`, applied over the inherited type.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TableTypeOverride {
    /// Absent or `inherit`: keep the inherited type.
    Inherit,
    Permanent,
    Transient,
}
