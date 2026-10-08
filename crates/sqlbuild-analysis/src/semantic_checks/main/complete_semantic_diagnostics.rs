//! Diagnostic recovery, explanations and opt-out rejection after the metadata checks.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::semantic_checks::_helpers::completion::complete;
use crate::semantic_checks::models::{CompletionOutcome, CompletionRequest, SemanticDeferral};
use crate::semantic_validation::models::ProjectCatalog;

/// Python's recovery, explanation and opt-out rejection, on the compile's analysis pool.
pub fn complete_semantic_diagnostics(
    request: &CompletionRequest,
    catalog: &ProjectCatalog,
) -> Result<CompletionOutcome, String> {
    let pool = catalog.analysis_pool()?;
    Ok(pool.install(|| {
        catch_compiler_panic(|| Ok(complete(request)))
            .unwrap_or(CompletionOutcome::Deferred(SemanticDeferral::NativeFailure))
    }))
}
