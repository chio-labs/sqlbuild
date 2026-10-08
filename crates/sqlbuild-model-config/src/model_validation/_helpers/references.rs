//! `validate_model_references` for references every discovered name resolves.

use crate::model_validation::constants::{
    REF_KIND, SEED_KIND, SOURCE_KIND, TABLE_FUNCTION_KIND, UDF_KIND,
};
use crate::model_validation::models::{ModelReference, ProjectValidationFacts, Rejected};
use crate::model_validation::types::Check;

/// Accept references that name discovered resources of their own kind.
pub(crate) fn check_references(
    references: &[ModelReference],
    project: &ProjectValidationFacts,
) -> Check {
    let resolves = |reference: &ModelReference| {
        let name = &reference.name;
        match reference.kind.as_str() {
            REF_KIND => project.models.contains(name),
            SEED_KIND => project.seeds.contains(name),
            SOURCE_KIND => project.sources.contains(name),
            UDF_KIND => project.functions.contains(name) && !project.table_functions.contains(name),
            TABLE_FUNCTION_KIND => {
                project.functions.contains(name) && project.table_functions.contains(name)
            }
            _ => false,
        }
    };
    if references.iter().all(resolves) {
        Ok(())
    } else {
        Err(Rejected)
    }
}
