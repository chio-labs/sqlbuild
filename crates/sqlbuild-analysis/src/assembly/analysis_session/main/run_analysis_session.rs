//! Run a native model analysis session over every wave.

use crate::assembly::analysis_session::models::{AnalysisSession, SessionStep};

/// Analyse every wave; any internal native failure fails the whole analysis.
pub fn run_analysis_session(session: &mut AnalysisSession) -> Result<SessionStep, String> {
    session.run()
}
