//! `_merge_target_config`: a project target with its local overrides.

use std::hash::Hash;

use crate::effective::_helpers::entries::updated;
use crate::effective::constants::TARGET_FIELDS;
use crate::effective::models::{FieldValue, MergeRule, TargetField, TargetLayer};

/// Whether the local layer sets the field of `group` named `name`.
fn sets<K, V>(local: &TargetLayer<K, V>, group: Option<&str>, name: &str) -> bool {
    TARGET_FIELDS
        .iter()
        .zip(&local.fields)
        .find(|(field, _)| field.group == group && field.name == name)
        .is_some_and(|(_, value)| value.is_set())
}

/// One field's merged value.
fn merged_field<K: Eq + Hash + Clone, V: Clone>(
    field: &TargetField,
    project: &FieldValue<K, V>,
    local: &FieldValue<K, V>,
    local_layer: &TargetLayer<K, V>,
) -> FieldValue<K, V> {
    let decides = |decided_by: &[&str]| {
        decided_by
            .iter()
            .any(|name| sets(local_layer, field.group, name))
    };
    match (field.rule, project, local) {
        (MergeRule::Union, FieldValue::Map(project), FieldValue::Map(local)) => {
            let merged = updated(
                project.clone().unwrap_or_default(),
                local.as_deref().unwrap_or_default(),
            );
            FieldValue::Map(Some(merged))
        }
        (MergeRule::ReplaceOrEmpty { decided_by }, _, FieldValue::Map(local))
            if decides(decided_by) =>
        {
            FieldValue::Map(Some(local.clone().unwrap_or_default()))
        }
        (MergeRule::Overlay { decided_by }, _, _) if decides(decided_by) => local.clone(),
        _ => project.clone(),
    }
}

/// The project target, or with a local target each field merged by its rule.
#[must_use]
pub fn merged_target<K: Eq + Hash + Clone, V: Clone>(
    project: TargetLayer<K, V>,
    local: Option<&TargetLayer<K, V>>,
) -> TargetLayer<K, V> {
    let Some(local) = local else {
        return project;
    };
    TargetLayer {
        fields: TARGET_FIELDS
            .iter()
            .zip(project.fields.iter().zip(&local.fields))
            .map(|(field, (project, local_value))| merged_field(field, project, local_value, local))
            .collect(),
    }
}
