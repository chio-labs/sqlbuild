//! A planned model as its materialization labels read it.

/// The plan-entry fields materialization labels read.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ModelLabelFacts {
    pub materialization_type: String,
    pub action: String,
    pub custom_materialization_name: Option<String>,
    pub incremental_strategy: Option<String>,
    pub incremental_mode: Option<String>,
    pub cursor_type: Option<String>,
    pub snapshot_strategy: Option<String>,
    /// The snapshot records an `observed_at` column.
    pub historical: bool,
    pub historical_input: Option<String>,
}

/// A cursor bound value parsed as an ISO date or datetime.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ParsedBound {
    /// The value's calendar date as `YYYY-MM-DD`.
    pub date: String,
    /// Hour, minute, second and microsecond are all zero.
    pub midnight: bool,
}

/// A cursor's type, strategy, declared grain and its inputs' grains, as the replay grain reads them.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct TimestampGrainFacts {
    pub cursor_type: Option<String>,
    pub microbatch_strategy: Option<String>,
    pub downstream_grain: Option<String>,
    pub input_grains: Vec<Option<String>>,
}
