//! The inputs and result of one model's config build.

use crate::config_presence::models::MacroPath;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::ConfigEntries;
use crate::errors::ConfigError;
use crate::model_validation::models::{RetentionOverride, TableTypeOverride};

/// The project-wide inputs every model's config build reads, captured once per compile.
#[derive(Clone, Debug)]
pub struct ConfigBuildInputs<H> {
    /// `project_defaults_to_mapping`'s entries.
    pub defaults: ConfigEntries<H>,
    /// Each path default's entries by its key.
    pub path_defaults: Vec<(String, ConfigEntries<H>)>,
    /// The effective vars.
    pub variables: ConfigEntries<H>,
    pub run_id: ConfigNode<H>,
    pub target_name: ConfigNode<H>,
    /// The active target's `(database, schema)`, without a target `None`.
    pub target_namespace: Option<(ConfigNode<H>, ConfigNode<H>)>,
}

/// What the native header parse found in one header entry.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HeaderEntryFacts {
    /// Whether a string in the value holds a `${...}` template.
    pub template: bool,
    /// Where the config macro walk finds a macro call.
    pub macro_path: MacroPath,
}

/// One model's authored header and, when it was parsed natively, each entry's facts by key.
#[derive(Clone, Copy, Debug)]
pub struct ModelHeader<'a, H> {
    pub entries: &'a [(ConfigNode<H>, ConfigNode<H>)],
    pub facts: Option<&'a [(String, HeaderEntryFacts)]>,
}

/// One model's built config, before the caller wraps it in `CompileModelConfig`.
#[derive(Clone, Debug)]
pub struct BuiltModelConfig<H> {
    pub values: ConfigEntries<H>,
    pub header_keys: Vec<String>,
    pub logical_schema: Option<ConfigNode<H>>,
    pub layer_schema_configured: bool,
    pub logical_database: Option<ConfigNode<H>>,
    pub retention: RetentionOverride,
    pub table_type: TableTypeOverride,
    /// The `(kind, name)` environment and context reads, in order.
    pub reads: Vec<(&'static str, String)>,
    /// The header keys whose built values are still the header's own values.
    pub own_header_keys: Vec<String>,
}

/// Why a build stops: the config error it raises, a caller error, or a header key that is not text.
#[derive(Debug, PartialEq)]
pub enum ConfigBuildHalt<H, E> {
    Config(ConfigError),
    Host(E),
    /// A header key that is not a string, which Python fails to read as one.
    KeyNotText(ConfigNode<H>),
    /// A path default the inputs do not hold.
    MissingPathDefault(String),
}
