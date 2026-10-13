//! Source freshness command results.

/// Command status for one source freshness observation.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FreshnessStatus {
    Observed,
    Changed,
    Unchanged,
    Tolerated,
    Unknown,
    Error,
}

impl FreshnessStatus {
    /// The status as JSON output spells it.
    #[must_use]
    pub fn value(self) -> &'static str {
        match self {
            Self::Observed => "observed",
            Self::Changed => "changed",
            Self::Unchanged => "unchanged",
            Self::Tolerated => "tolerated",
            Self::Unknown => "unknown",
            Self::Error => "error",
        }
    }
}

/// Freshness observation result for one source.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FreshnessSourceResult {
    pub name: String,
    pub status: FreshnessStatus,
    pub strategy: Option<String>,
    pub value_kind: Option<String>,
    pub current_data_version: Option<String>,
    pub previous_data_version: Option<String>,
    pub lag_tolerance: Option<String>,
    pub target_database: Option<String>,
    pub target_schema: Option<String>,
    pub target_name: Option<String>,
    pub message: Option<String>,
    /// `pass`, `warn`, `error` or `unknown` when the source has an age policy.
    pub age_status: Option<String>,
}

impl FreshnessSourceResult {
    /// A result with only a name and status set.
    #[must_use]
    pub fn new(name: &str, status: FreshnessStatus) -> Self {
        Self {
            name: name.to_owned(),
            status,
            strategy: None,
            value_kind: None,
            current_data_version: None,
            previous_data_version: None,
            lag_tolerance: None,
            target_database: None,
            target_schema: None,
            target_name: None,
            message: None,
            age_status: None,
        }
    }
}

/// How a current observation compares to the previous state record.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StateComparison {
    /// State was not requested.
    NotCompared,
    /// State was requested and has no record for the source.
    Missing,
    /// The records are equivalent within tolerance, and whether their hashes are equal.
    Equivalent { same_hash: bool },
    /// The records differ beyond tolerance.
    Different,
}
