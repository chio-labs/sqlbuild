//! The target namespace check failures, with the values their messages name.

/// One target namespace check failure.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TargetError {
    /// A resource of an adapter that needs both parts resolved without some of them.
    MissingParts(MissingParts),
    /// Two targets on one connection write managed loader data to one namespace.
    LoaderCollision(LoaderCollision),
    /// A managed write, named by its label, without an explicit physical schema.
    ManagedWriteSchema(String),
    /// A named target without an explicit schema.
    NamedTargetSchema(String),
}

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
