//! Python's `recover_output_types` up to the revalidation Python runs on the binding catalog.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::semantic_checks::_helpers::type_recovery::plan;
use crate::semantic_checks::models::{SemanticDeferral, TypeRecoveryRequest, TypeRecoveryStep};
use crate::semantic_validation::models::ProjectCatalog;

/// Plan type recovery on the compile's analysis pool; a native panic defers to Python.
pub fn plan_type_recovery(
    request: &TypeRecoveryRequest,
    catalog: &ProjectCatalog,
) -> Result<TypeRecoveryStep, String> {
    let pool = catalog.analysis_pool()?;
    Ok(pool.install(|| {
        catch_compiler_panic(|| Ok(plan(request)))
            .unwrap_or(TypeRecoveryStep::Deferred(SemanticDeferral::NativeFailure))
    }))
}
