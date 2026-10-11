//! Reject factory audits whose identity a model's other audits already use.

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::factories::duplicate_identity;

/// `Ok` when every generated identity is new; `model` is `(model name, file path)`.
pub fn merged_audit_identities(
    direct: &[String],
    generated: &[String],
    model: (&str, &str),
) -> Result<(), ConfigError> {
    duplicate_identity(direct, generated, model.0, model.1)
}
