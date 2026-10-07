//! Native outcomes of reading and loading authored YAML files.

use crate::models::{DiscoveryFailure, ReadFailure};
use sqlbuild_config::models::ConfigValue;

/// One YAML file read and loaded as YAML 1.1 `safe_load`, or why it could not be.
#[derive(Clone, Debug, PartialEq)]
pub enum YamlFileOutcome {
    Loaded {
        contents: String,
        value: ConfigValue,
    },
    /// Invalid YAML, or YAML outside the forms SQLBuild reads.
    Failed(DiscoveryFailure),
    /// The file could not be read or decoded as Python's `read_text` would.
    Unreadable(ReadFailure),
}
