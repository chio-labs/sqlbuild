//! Python's `analyze_dynamic_column_contract` for one model outside the analysis session.

use crate::assembly::analysis_session::_helpers::dynamic_pivot::{PivotFacts, pivot_outcome};
use crate::assembly::analysis_session::constants::PIVOT_WORKER_STACK_BYTES;
use crate::assembly::analysis_session::models::{PivotOutcome, PivotRequest};

/// The model's proof, or a deferral where Python's result is not reproduced exactly.
pub fn prove_dynamic_contract(request: &PivotRequest) -> Result<PivotOutcome, String> {
    let facts = PivotFacts {
        dialect: &request.dialect,
        column_types: &request.column_types,
        authoritative_types: &request.authoritative_types,
        column_nullability: &request.column_nullability,
        families_by_table: &request.families_by_table,
    };
    std::thread::scope(|scope| {
        std::thread::Builder::new()
            .stack_size(PIVOT_WORKER_STACK_BYTES)
            .spawn_scoped(scope, || {
                pivot_outcome(&request.sql, &request.families, &facts)
            })
            .map_err(|error| error.to_string())?
            .join()
            .map_err(|_| "the native dynamic pivot proof panicked".to_owned())
    })
}
