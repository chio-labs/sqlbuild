//! A config mapping's entries.

use crate::config_values::models::ConfigNode;

/// A mapping's `(key, value)` entries in insertion order, as a Python `dict` keeps them.
pub type ConfigEntries<H> = Vec<(ConfigNode<H>, ConfigNode<H>)>;
