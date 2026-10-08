//! Accept a model's effective config when every Python model validator would.

use crate::model_validation::_helpers::config::ConfigView;
use crate::model_validation::_helpers::incremental::check_incremental;
use crate::model_validation::_helpers::materialization::{
    check_contract_and_incremental_keys, check_custom_materialization, check_migration,
    check_placeholders, check_project_capability, check_storage_policies,
};
use crate::model_validation::_helpers::references::check_references;
use crate::model_validation::_helpers::snapshot::check_snapshot;
use crate::model_validation::models::{ModelValidationFacts, ProjectValidationFacts};
use crate::model_validation::types::Check;
use crate::types::AuthoredNode;

/// Accept only what every Python validator accepts; a rejection means Python must decide.
pub fn accept_model_config<N: AuthoredNode>(
    entries: Vec<(N, N)>,
    project: &ProjectValidationFacts,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let config = ConfigView::new(entries);
    check_references(facts.references, project)?;
    check_incremental(&config, facts)?;
    check_project_capability(&config, project)?;
    check_contract_and_incremental_keys(&config)?;
    check_snapshot(&config, facts)?;
    check_custom_materialization(&config, project)?;
    check_storage_policies(&config, facts)?;
    check_migration(&config, facts)?;
    check_placeholders(&config, project, facts)
}
