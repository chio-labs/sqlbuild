//! The target namespace check failures, with the values their messages name.

/// A resource whose relation location misses a database or schema.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MissingParts {
    pub adapter_name: String,
    pub resource_kind: String,
    pub resource_name: String,
    pub database: Option<String>,
    pub schema: Option<String>,
}

/// Two targets and the first namespace they share.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LoaderCollision {
    pub left_target: String,
    pub right_target: String,
    pub database: Option<String>,
    pub schema: Option<String>,
}
