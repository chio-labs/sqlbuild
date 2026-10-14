//! Graph key namespaces and path selector syntax.

/// Owner namespace of dbt nodes.
pub const DBT_OWNER: &str = "dbt";
/// Owner namespace of SQLBuild nodes.
pub const SQLBUILD_OWNER: &str = "sqb";
/// Resource type namespace of models.
pub const MODEL_RESOURCE_TYPE: &str = "model";
/// Resource type namespace of dbt sources and seeds.
pub const SOURCE_RESOURCE_TYPE: &str = "source";
/// Separator between the two endpoints of a path selector.
pub const PATH_SELECTOR_SEPARATOR: &str = "~";
/// Diagnostic code of an invalid path selector.
pub const PATH_SELECTOR_ERROR_CODE: &str = "C237";
/// Prefix of an exact dbt FQN selector.
pub const FQN_SELECTOR_PREFIX: &str = "fqn:";
