//! Facts about one logging record that routing decisions read.

/// One record's logger family, level and SQL fields.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RecordFacts {
    /// The record comes from the SQLBuild logger or one of its children.
    pub internal: bool,
    pub level: i64,
    /// The record carries a SQL digest field.
    pub has_sql_digest: bool,
    /// The record carries a SQL text field.
    pub has_sql_text: bool,
}

/// Which records one diagnostic destination receives.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RouteOptions {
    /// Only SQLBuild records reach this destination.
    pub internal_only: bool,
    /// SQLBuild records reach this destination.
    pub allow_internal: bool,
    /// This destination receives SQL text, so it only accepts records that carry it.
    pub include_sql_text: bool,
}
