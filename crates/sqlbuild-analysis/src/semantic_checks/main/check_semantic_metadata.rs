//! Python's semantic metadata checks after type recovery, without the Polyglot wheel.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::semantic_checks::_helpers::metadata_checks::checks::check_metadata;
use crate::semantic_checks::models::{MetadataOutcome, MetadataRequest, SemanticDeferral};
use crate::semantic_validation::models::ProjectCatalog;

/// Check metadata on the compile's analysis pool; a deferral hands the checks back to Python.
pub fn check_semantic_metadata(
    request: &MetadataRequest,
    catalog: &ProjectCatalog,
) -> Result<Result<MetadataOutcome, SemanticDeferral>, String> {
    let pool = catalog.analysis_pool()?;
    Ok(pool.install(|| {
        catch_compiler_panic(|| Ok(check_metadata(request)))
            .unwrap_or(Err(SemanticDeferral::NativeFailure))
    }))
}
