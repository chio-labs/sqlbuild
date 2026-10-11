//! `validate_preserved_logical_namespace`: a target that preserves needs a logical namespace.

use crate::assembly::project::_helpers::targets::preserved_namespace;
use crate::assembly::project::errors::AssemblyError;
use crate::assembly::project::models::TargetNamespace;

/// The error Python raises when `target` preserves a dimension the resource has no logical value for.
pub fn preserved_logical_namespace(
    resource_label: &str,
    target: Option<&TargetNamespace>,
    logical: (Option<&String>, Option<&String>),
) -> Result<(), AssemblyError> {
    preserved_namespace(resource_label, target, logical.0, logical.1)
}
