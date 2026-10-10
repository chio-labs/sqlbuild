//! Diagnostic recovery, explanations and opt-out rejection after the metadata checks.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::semantic_checks::_helpers::explanation::completion::complete;
use crate::semantic_checks::models::{CompletionOutcome, CompletionRequest, SemanticFailure};
use crate::semantic_validation::models::ProjectCatalog;

/// Python's recovery, explanation and opt-out rejection, on the compile's analysis pool.
///
/// # Errors
///
/// The error Python's completion raised for the same input, or an internal native failure.
pub fn complete_semantic_diagnostics(
    request: &CompletionRequest,
    catalog: &ProjectCatalog,
) -> Result<CompletionOutcome, SemanticFailure> {
    let pool = catalog.analysis_pool().map_err(SemanticFailure::Internal)?;
    pool.install(|| {
        catch_compiler_panic(|| Ok(complete(request))).map_err(SemanticFailure::Internal)?
    })
}
