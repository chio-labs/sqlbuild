//! The loaded project configuration, described as the Python objects it projects to.

use crate::models::ConfigValue;

/// One configuration file a loader reads or names in a message.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ConfigFile {
    Project,
    LegacyProject,
    Local,
    LegacyLocal,
}

/// The paths of the project and local configuration files and their legacy YAML names.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConfigPaths {
    pub project: std::path::PathBuf,
    pub legacy_project: std::path::PathBuf,
    pub local: std::path::PathBuf,
    pub legacy_local: std::path::PathBuf,
}

/// A loaded value, as the Python value or dataclass instance it projects to.
#[derive(Clone, Debug, PartialEq)]
pub enum Built {
    /// A plain value, including `None`, booleans, integers and raw authored mappings.
    Value(ConfigValue),
    /// A native project configuration record; omitted fields keep their defaults.
    Object(&'static str, Vec<(&'static str, Built)>),
    /// A member of a named `StrEnum`, by value.
    Enum(&'static str, String),
    /// A `dict` with string keys, in insertion order.
    Dict(Vec<(String, Built)>),
    /// A `tuple` of strings.
    Tuple(Vec<String>),
    /// A `frozenset` of strings.
    FrozenSet(Vec<String>),
    /// `Decimal(str(value))` of an integer or float.
    Decimal(ConfigValue),
}

/// A setting value as help text shows it in TOML.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SettingText {
    Bool(bool),
    /// An integer, as its decimal text.
    Integer(String),
    Text(String),
}

/// Where a setting lives: its file name, TOML section and key.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SettingSite<'a> {
    pub file_name: &'a str,
    pub section: &'a str,
    pub key: &'a str,
}
