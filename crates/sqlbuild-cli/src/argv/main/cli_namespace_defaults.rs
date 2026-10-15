//! The attribute defaults every new `CliNamespace` starts from.

use crate::argv::constants::CLI_NAMESPACE_DEFAULTS;
use crate::argv::models::NamespaceDefault;

/// Every defaulted `CliNamespace` attribute and its default, in declaration order.
#[must_use]
pub fn cli_namespace_defaults() -> &'static [(&'static str, NamespaceDefault)] {
    &CLI_NAMESPACE_DEFAULTS
}
