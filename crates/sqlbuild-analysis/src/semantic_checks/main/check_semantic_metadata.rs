//! Python's semantic metadata checks after type recovery, without the Polyglot wheel.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::semantic_checks::_helpers::metadata_checks::checks::check_metadata;
use crate::semantic_checks::models::{MetadataOutcome, MetadataRequest, SemanticFailure};
use crate::semantic_validation::models::ProjectCatalog;

/// Check metadata on the compile's analysis pool.
///
/// # Errors
///
/// The error Python's checks raised for the same input, or an internal native failure.
pub fn check_semantic_metadata(
    request: &MetadataRequest,
    catalog: &ProjectCatalog,
) -> Result<MetadataOutcome, SemanticFailure> {
    let pool = catalog.analysis_pool().map_err(SemanticFailure::Internal)?;
    pool.install(|| {
        catch_compiler_panic(|| Ok(check_metadata(request))).map_err(SemanticFailure::Internal)?
    })
}
