//! Validate one model's references on their own, as its hook references are checked.

use crate::model_validation::_helpers::references::check_references;
use crate::model_validation::models::{
    ModelValidationFacts, ProjectValidationFacts, ValidationStop,
};

/// Check each reference in order, stopping at the first unknown or misused one.
pub fn validate_model_references(
    project: &ProjectValidationFacts,
    facts: &ModelValidationFacts<'_>,
) -> Result<(), ValidationStop> {
    check_references(facts, project)
}
