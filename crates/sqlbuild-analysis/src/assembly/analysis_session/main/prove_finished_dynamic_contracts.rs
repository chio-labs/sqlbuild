//! Python's `analyze_dynamic_column_contract` for models outside a finished analysis session.

use crate::assembly::analysis_session::_helpers::dynamic_pivot::pooled_pivot_outcomes;
use crate::assembly::analysis_session::models::{FinishedSession, PivotModel, PivotOutcome};

/// Each model's proof in order from the session's own tables; a panicking proof is deferred.
pub fn prove_finished_dynamic_contracts(
    session: &FinishedSession,
    models: &[PivotModel],
) -> Result<Vec<PivotOutcome>, String> {
    let pool = session.pool.as_ref().map_err(Clone::clone)?;
    Ok(pooled_pivot_outcomes(pool, models, &session.tables))
}
