//! Native outcomes of reading and loading authored YAML files.

use sqlbuild_config::models::ConfigValue;

/// One YAML file read and loaded as PyYAML `safe_load` would, or what Python must redo.
#[derive(Clone, Debug, PartialEq)]
pub enum YamlFileOutcome {
    Loaded {
        contents: String,
        value: ConfigValue,
    },
    /// Read, but the native loader cannot reproduce PyYAML here; Python loads the contents.
    LoadInPython { contents: String },
    /// The bytes could not be read or decoded; Python re-reads the file to raise its error.
    Unreadable,
}
