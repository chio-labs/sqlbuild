//! Resume a native model analysis session with Python's answers.

use crate::assembly::analysis_session::models::{AnalysisSession, DeferredAnalysis};

/// Answer the deferrals of the session's last step.
pub fn provide_deferred_analyses(
    session: &mut AnalysisSession,
    results: Vec<DeferredAnalysis>,
) -> Result<(), String> {
    session.provide(results)
}
