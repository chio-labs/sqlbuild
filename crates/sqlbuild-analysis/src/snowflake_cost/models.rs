//! The run attribution a SQLBuild Snowflake query tag carries.

/// Non-empty string fields of a SQLBuild query tag.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct QueryTag {
    pub run_id: Option<String>,
    pub resource_type: Option<String>,
    pub resource_name: Option<String>,
}
