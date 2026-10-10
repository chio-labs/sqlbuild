//! Python's `recover_output_types` up to the revalidation Python runs on the binding catalog.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::semantic_checks::_helpers::recovery::type_recovery::plan;
use crate::semantic_checks::models::{SemanticFailure, TypeRecoveryRequest, TypeRecoveryStep};
use crate::semantic_validation::models::ProjectCatalog;

/// Plan type recovery on the compile's analysis pool.
///
/// # Errors
///
/// The error Python's recovery raised for the same input, or an internal native failure.
pub fn plan_type_recovery(
    request: &TypeRecoveryRequest,
    catalog: &ProjectCatalog,
) -> Result<TypeRecoveryStep, SemanticFailure> {
    let pool = catalog.analysis_pool().map_err(SemanticFailure::Internal)?;
    pool.install(|| {
        catch_compiler_panic(|| Ok(plan(request))).map_err(SemanticFailure::Internal)?
    })
}
