//! `singular_audit_resources`: what a singular audit reads, and why it is not cross-resource.

use std::collections::BTreeSet;

use crate::audits::_helpers::resources::{companion_resource, single_resource_problem};
use crate::audits::constants::{CROSS_MODEL_MINIMUM, MODEL_RESOURCE, REF_KIND};
use crate::audits::models::SingularAuditResources;

/// The sorted `(kind, name)` resources `references` read and the P004 problem, if any.
#[must_use]
pub fn singular_audit_resources(references: &[(&str, &str)]) -> SingularAuditResources {
    let mut models: BTreeSet<&str> = BTreeSet::new();
    let mut companions: BTreeSet<(&'static str, &str)> = BTreeSet::new();
    for &(kind, name) in references {
        if kind == REF_KIND {
            models.insert(name);
        } else if let Some(resource) = companion_resource(kind) {
            companions.insert((resource, name));
        }
    }
    let mut resources: BTreeSet<(String, String)> = models
        .iter()
        .map(|name| (MODEL_RESOURCE.to_owned(), (*name).to_owned()))
        .collect();
    resources.extend(
        companions
            .iter()
            .map(|(kind, name)| ((*kind).to_owned(), (*name).to_owned())),
    );
    let problem = (models.len() < CROSS_MODEL_MINIMUM
        && (models.is_empty() || companions.is_empty()))
    .then(|| single_resource_problem(&models, !companions.is_empty()));
    SingularAuditResources {
        resources: resources.into_iter().collect(),
        problem,
    }
}
