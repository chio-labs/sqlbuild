//! The message of a rejected qualified identity.

use sqlbuild_core::text::main::python_str_repr::python_str_repr;

use crate::scope_index::models::IdentityFailure;

/// Python's `InvalidQualifiedIdentityError` message for a rejected identity.
#[must_use]
pub fn identity_failure_message(failure: &IdentityFailure, value: &str) -> String {
    let shown = |text: &str| -> String { python_str_repr(text) };
    match failure {
        IdentityFailure::NoName => format!("Qualified identity has no name: {}", shown(value)),
        IdentityFailure::UnknownKind(kind) => {
            format!("Unknown qualified identity kind: {}", shown(kind))
        }
        IdentityFailure::InvalidPrivate => format!("Invalid private identity: {}", shown(value)),
        IdentityFailure::Unqualified => format!(
            "Expected a kind-qualified identity such as 'model:name': {}",
            shown(value)
        ),
    }
}
