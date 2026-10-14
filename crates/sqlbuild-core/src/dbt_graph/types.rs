//! Caller-supplied SQLBuild selector behaviour.

use crate::dbt_graph::models::DbtSelectorExpansion;

/// The caller's SQLBuild selector parsing and model name resolution.
pub trait DbtSelectorResolver {
    /// The caller's failure type.
    type Error;
    /// Split `+` expansion markers from one selector term.
    fn split(&self, term: &str) -> Result<DbtSelectorExpansion, Self::Error>;
    /// SQLBuild model names one selector core matches, and its path translation.
    fn model_names(&self, core: &str) -> Result<(Vec<String>, Option<String>), Self::Error>;
}
