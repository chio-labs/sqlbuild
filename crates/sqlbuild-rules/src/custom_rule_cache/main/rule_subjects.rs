//! `rule_subjects`: the invocations one custom rule runs, with each subject's identity.

use crate::custom_rule_cache::_helpers::digest::{field_digest, optional_fields};
use crate::custom_rule_cache::constants::{
    MODEL_SUBJECT_KIND, PROJECT_SUBJECT, PROJECT_SUBJECT_KIND, PROJECT_SUBJECT_NAME,
};
use crate::custom_rule_cache::models::{ModelSubjectInput, Subject, SubjectsInput};

/// The project subject for project-wide rules, otherwise every model sorted by path.
#[must_use]
pub fn rule_subjects(subject: Option<&str>, input: &SubjectsInput) -> Vec<Subject> {
    if subject == Some(PROJECT_SUBJECT_NAME) {
        let [has_target, target] = optional_fields(input.target_name.as_deref());
        let count: String = input.models.len().to_string();
        return vec![Subject {
            key: PROJECT_SUBJECT.to_owned(),
            identity: field_digest(PROJECT_SUBJECT_KIND, &[&count, has_target, target]),
        }];
    }
    let mut models: Vec<&ModelSubjectInput> = input.models.iter().collect();
    models.sort_by(|left, right| left.path.cmp(&right.path));
    models
        .into_iter()
        .map(|model| {
            let [has_materialized, materialized] = optional_fields(model.materialized.as_deref());
            Subject {
                key: model.path.clone(),
                identity: field_digest(
                    MODEL_SUBJECT_KIND,
                    &[&model.name, &model.path, has_materialized, materialized],
                ),
            }
        })
        .collect()
}
