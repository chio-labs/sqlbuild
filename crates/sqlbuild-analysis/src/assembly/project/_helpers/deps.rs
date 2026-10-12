//! Python's dependency keys for compiled resources (`compile/_helpers/deps/dependencies.py`).

use std::collections::HashSet;

use sqlbuild_core::text::main::python_str_repr::python_str_repr;

use crate::assembly::project::constants::{
    ATTACHED_AUDIT_KINDS, AUDIT_TARGET_KIND_ENUM, DBT_REF_KIND, KIND_RESOURCES, MODEL_RESOURCE,
};
use crate::assembly::project::errors::AssemblyError;
use crate::assembly::project::models::{AuditFacts, Reference};
use crate::assembly::project::types::Fact;
use crate::assembly::project::types::ObjectKey;

/// `model_build_deps` and `function_build_deps`: each reference's key, first occurrence kept.
pub(crate) fn reference_deps(references: &[Reference]) -> Vec<ObjectKey> {
    deduped(references.iter().map(reference_dep).collect())
}

/// `audit_scope_deps`: the references, then the attached resource, first occurrence kept.
pub(crate) fn audit_deps(audit: &AuditFacts) -> Fact<Vec<ObjectKey>> {
    let mut keys: Vec<ObjectKey> = reference_deps(&audit.references);
    if let Some((kind, name)) = &audit.attached {
        if !ATTACHED_AUDIT_KINDS.contains(&kind.as_str()) {
            let repr: String = python_str_repr(kind);
            return Err(AssemblyError::Value(format!(
                "{repr} is not a valid {AUDIT_TARGET_KIND_ENUM}"
            )));
        }
        keys.push((kind.clone(), name.clone()));
    }
    Ok(deduped(keys))
}

/// `_reference_dep`.
fn reference_dep(reference: &Reference) -> ObjectKey {
    let kind: &str = reference.kind.as_str();
    if KIND_RESOURCES.contains(&kind) {
        return (kind.to_owned(), reference.name.clone());
    }
    if kind == DBT_REF_KIND {
        let name: String = match &reference.package {
            Some(package) => format!("{package}.{}", reference.name),
            None => reference.name.clone(),
        };
        return (DBT_REF_KIND.to_owned(), name);
    }
    (MODEL_RESOURCE.to_owned(), reference.name.clone())
}

/// `_dedupe_object_keys`.
fn deduped(keys: Vec<ObjectKey>) -> Vec<ObjectKey> {
    let mut seen: HashSet<ObjectKey> = HashSet::new();
    keys.into_iter()
        .filter(|key| seen.insert(key.clone()))
        .collect()
}
