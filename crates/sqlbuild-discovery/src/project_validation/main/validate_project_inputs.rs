//! Python's `validate_discovered_inputs`: cross-file conflicts across discovered project inputs.

use crate::project_validation::_helpers::declarations::validate_declarations;
use crate::project_validation::_helpers::file_names::validate_file_names;
use crate::project_validation::_helpers::identities::validate_identities;
use crate::project_validation::_helpers::loaders::validate_loaders;
use crate::project_validation::_helpers::path_defaults::validate_path_defaults;
use crate::project_validation::_helpers::resource_names::validate_unique_project_resource_names;
use crate::project_validation::_helpers::seeds::validate_declared_seed_files;
use crate::project_validation::models::{ProjectFacts, ValidationFailure};

/// Validate cross-file conflicts in Python's order; the first conflict is reported.
pub fn validate_project_inputs(facts: &ProjectFacts) -> Result<(), ValidationFailure> {
    validate_identities(facts)?;
    validate_file_names(facts)?;
    validate_loaders(facts)?;
    validate_declarations(facts)?;
    validate_declared_seed_files(facts)?;
    validate_unique_project_resource_names(facts)?;
    validate_path_defaults(facts)
}
