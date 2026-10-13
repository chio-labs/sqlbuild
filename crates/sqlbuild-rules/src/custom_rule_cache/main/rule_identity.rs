//! `rule_identity`: everything besides fact reads that keys one custom rule's stored results.

use crate::custom_rule_cache::_helpers::digest::{field_digest, optional_fields};
use crate::custom_rule_cache::constants::RULE_KIND;
use crate::custom_rule_cache::models::RuleIdentityInput;

/// A digest of the code identity, host runtime, rule metadata and source, config, dialect and root.
#[must_use]
pub fn rule_identity(input: &RuleIdentityInput) -> String {
    let [has_subject, subject] = optional_fields(input.subject.as_deref());
    field_digest(
        RULE_KIND,
        &[
            &input.code_identity,
            &input.runtime_version,
            &input.code,
            &input.family,
            &input.slug,
            &input.message,
            &input.remediation,
            has_subject,
            subject,
            &input.implementation_fingerprint,
            &input.config_json,
            &input.dialect,
            &input.project_dir,
        ],
    )
}
