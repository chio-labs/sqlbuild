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

/// One value loaded from a dbt YAML file, as project and profile loading tell values apart.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DbtYamlValue {
    /// `None`, or a key the mapping does not have.
    Null,
    Text(String),
    /// A mapping and whether it has no entries.
    Mapping {
        empty: bool,
    },
    /// Any other value.
    Other,
}

/// The `dbt_project.yml` settings profile resolution needs.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DbtProjectMetadata {
    pub project_name: String,
    pub profile_name: String,
    pub target_path: String,
}

/// One profile of `profiles.yml` as loaded: the profile, its outputs, their entries and its target.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LoadedDbtProfile {
    pub profile: DbtYamlValue,
    pub outputs: DbtYamlValue,
    /// Each `(name, output)` of `outputs` in file order, when `outputs` is a mapping.
    pub output_entries: Vec<(DbtYamlValue, DbtYamlValue)>,
    pub target: DbtYamlValue,
}

/// A validated profile: its name, default target, and each output name with its entry index.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DbtProfileOutputs {
    pub name: String,
    pub default_target: Option<String>,
    /// Stripped output names in first-seen order; a repeated name keeps its last entry.
    pub outputs: Vec<(String, usize)>,
}

/// How dbt's `as_number` parses one stripped text.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DbtNumberParse {
    Integer,
    Float,
}
