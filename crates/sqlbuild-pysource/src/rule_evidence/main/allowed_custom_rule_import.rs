//! The deterministic import allowlist of custom-rule code.

use crate::rule_evidence::constants::{CUSTOM_RULE_IMPORT_ROOTS, MODULE_SEPARATOR};

/// Whether custom-rule code may import the absolute module `module`.
#[must_use]
pub fn allowed_custom_rule_import(module: &str) -> bool {
    CUSTOM_RULE_IMPORT_ROOTS.iter().any(|root| {
        module
            .strip_prefix(root)
            .is_some_and(|rest| rest.is_empty() || rest.starts_with(MODULE_SEPARATOR))
    })
}
