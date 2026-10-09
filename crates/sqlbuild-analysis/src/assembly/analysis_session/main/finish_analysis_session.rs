//! Collect a finished native model analysis session's outcomes.

use crate::assembly::analysis_session::models::{AnalysisSession, FinishedSession, SessionOutcome};

/// Every model's outcome and catalog changes, and the session kept for later pivot proofs.
pub fn finish_analysis_session(
    session: AnalysisSession,
) -> Result<(SessionOutcome, FinishedSession), String> {
    session.finish()
}
