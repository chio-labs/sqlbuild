//! Advance a native model analysis session to its next deferrals.

use crate::assembly::analysis_session::models::{AnalysisSession, SessionStep};

/// Advance until Python must answer deferrals; a step without deferrals means done.
pub fn run_analysis_session(session: &mut AnalysisSession) -> Result<SessionStep, String> {
    session.run()
}
