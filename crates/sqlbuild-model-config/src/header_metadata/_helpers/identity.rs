//! `validate_resource_identity`, with its suggested snake_case spelling.

use crate::errors::{ConfigError, ErrorClass};
use crate::resource_identities::main::resource_identity_failure::resource_identity_failure;

/// Raise `ResourceIdentityError` unless `name` is canonical snake_case.
pub(crate) fn check_identity(name: &str, kind: &str, path: &str) -> Result<(), ConfigError> {
    let Some((suggestion, help)) = resource_identity_failure(name, false) else {
        return Ok(());
    };
    Err(ConfigError::compile(format!(
        "Invalid {kind} identity '{name}' in {path}; use snake_case '{suggestion}'"
    ))
    .with_class(ErrorClass::ResourceIdentity)
    .with_help(help))
}
