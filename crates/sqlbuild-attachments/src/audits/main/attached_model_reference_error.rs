//! `validate_model_attached_audit_references`: a model's audit must read that model.

use crate::audits::constants::{MODEL_RESOURCE, REF_KIND};

/// The error when a model-attached audit's references (`(kind, name)`) skip the model.
#[must_use]
pub fn attached_model_reference_error(
    audit_label: &str,
    attached: (&str, &str),
    references: &[(&str, &str)],
) -> Option<String> {
    let (kind, name) = attached;
    if kind != MODEL_RESOURCE {
        return None;
    }
    if references.iter().any(|&(reference_kind, reference_name)| {
        reference_kind == REF_KIND && reference_name == name
    }) {
        return None;
    }
    Some(format!(
        "{audit_label}: model-attached audit must reference the attached model '{name}' via __ref()"
    ))
}
