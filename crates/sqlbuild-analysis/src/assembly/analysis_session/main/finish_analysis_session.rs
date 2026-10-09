//! Collect a finished native model analysis session's outcomes.

use crate::assembly::analysis_session::models::{AnalysisSession, SessionOutcome};

/// Every model's outcome and the binding catalog changes Python records.
pub fn finish_analysis_session(session: AnalysisSession) -> Result<SessionOutcome, String> {
    session.finish()
}
