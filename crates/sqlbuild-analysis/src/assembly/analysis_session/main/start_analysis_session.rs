//! Start Python's uncached model analysis as a native session.

use crate::assembly::analysis_session::models::{AnalysisSession, SessionRequest};
use crate::semantic_validation::models::ProjectCatalog;

/// A session over `request` on a copy of `catalog`.
///
/// # Errors
///
/// An internal native failure where the request breaks the session's invariants.
pub fn start_analysis_session(
    request: SessionRequest,
    catalog: &ProjectCatalog,
) -> Result<AnalysisSession, String> {
    AnalysisSession::start(request, catalog)
}
