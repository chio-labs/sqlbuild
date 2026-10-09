//! Python's `analyze_dynamic_column_contract` for models no analysis session analysed.

use crate::assembly::analysis_session::_helpers::dynamic_pivot::pivot_outcomes;
use crate::assembly::analysis_session::constants::PIVOT_WORKER_STACK_BYTES;
use crate::assembly::analysis_session::models::{PivotBatchRequest, PivotOutcome};

/// Each model's proof in order; a model whose proof panics is deferred to Python.
pub fn prove_dynamic_contracts(request: &PivotBatchRequest) -> Result<Vec<PivotOutcome>, String> {
    std::thread::scope(|scope| {
        std::thread::Builder::new()
            .stack_size(PIVOT_WORKER_STACK_BYTES)
            .spawn_scoped(scope, || pivot_outcomes(&request.models, &request.tables))
            .map_err(|error| error.to_string())?
            .join()
            .map_err(|_| "the native dynamic pivot proofs panicked".to_owned())
    })
}
