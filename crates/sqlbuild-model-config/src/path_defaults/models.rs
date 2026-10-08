//! The outcome of selecting one model's path default.

use crate::errors::ConfigError;

/// The selected path-default key, or a conflict Python reports.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PathDefaultChoice {
    /// The nearest matching key, or `None` when no key matches.
    Selected(Option<String>),
    /// Several equally specific wildcard keys match; the `DiscoveryConflictError` Python raises.
    Conflict(ConfigError),
}
