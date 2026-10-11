//! Validate one MODEL header's `audit_factories` against the discovered factories.

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::factories::factory_references;
use crate::types::AuthoredNode;

/// The referenced factory names in order; `model` is `(model name, file path)`.
pub fn audit_factory_references<N: AuthoredNode>(
    raw: &N,
    model: (&str, &str),
    available: &[String],
) -> Result<Vec<String>, ConfigError> {
    factory_references(raw, model.0, model.1, available)
}
