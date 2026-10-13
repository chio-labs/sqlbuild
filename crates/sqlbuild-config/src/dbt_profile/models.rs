//! A rendered dbt profile output and the SQLBuild connection built from it.

/// One profile output value, as normalization tells values apart.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ProfileValue {
    /// `None`.
    Null,
    /// `True` or `False`.
    Bool(bool),
    Text(String),
    /// Any other value; copied through unchanged.
    Other,
}

/// One `key: value` entry of a profile output, in output order; non-string keys have no name.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProfileEntry {
    pub key: Option<String>,
    pub value: ProfileValue,
}

/// Where one connection value comes from.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ConnectionSource {
    /// The value of the output entry at this index.
    Entry(usize),
    /// A literal default.
    Text(&'static str),
}

/// The key one connection value is written under.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ConnectionKey {
    Name(&'static str),
    /// The key of the output entry at this index, unchanged.
    Entry(usize),
}

/// A normalized SQLBuild connection: its adapter, ordered values, target namespace and warnings.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NormalizedProfile {
    pub adapter: &'static str,
    pub connection: Vec<(ConnectionKey, ConnectionSource)>,
    pub target_schema: Option<String>,
    pub target_database: Option<String>,
    pub warnings: Vec<String>,
}

/// The values `sqb dbt init` writes into `sqlbuild_project.toml`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DbtInitConfig {
    pub project_name: String,
    pub adapter: String,
    pub target_name: String,
    pub profile_name: String,
    pub dbt_project_dir: String,
    pub profiles_dir: String,
    pub target_path: String,
    pub target_schema: Option<String>,
    pub target_database: Option<String>,
}
