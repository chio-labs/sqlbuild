//! Python's `recover_output_types` after revalidating the planned models with unknown types.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::semantic_checks::_helpers::recovery::type_recovery::finish;
use crate::semantic_checks::models::{TypeRecoveryOutcome, TypeRecoveryPlan, TypeRecoveryRequest};
use crate::semantic_checks::types::RevisedBinding;

/// Retained diagnostics and model bindings; a native panic is returned as its message.
pub fn finish_type_recovery(
    request: &TypeRecoveryRequest,
    plan: &TypeRecoveryPlan,
    revised: &[Vec<RevisedBinding>],
) -> Result<TypeRecoveryOutcome, String> {
    catch_compiler_panic(|| Ok(finish(request, plan, revised)))
}
