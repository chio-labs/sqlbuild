//! How many of a session's analysed models shared a query, and how many it re-analysed.

use crate::assembly::analysis_session::models::AnalysisSession;

/// `(shared members, shared members re-analysed alone)` across the session's batches so far.
pub fn session_sharing(session: &AnalysisSession) -> (usize, usize) {
    session.catalog.sharing()
}
