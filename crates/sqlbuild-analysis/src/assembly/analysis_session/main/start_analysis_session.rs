//! Start Python's uncached model analysis as a native session.

use crate::assembly::analysis_session::models::{AnalysisSession, SessionRequest};
use crate::semantic_validation::models::ProjectCatalog;

/// A session over `request` on a copy of `catalog`, or None where Python must analyse.
pub fn start_analysis_session(
    request: SessionRequest,
    catalog: &ProjectCatalog,
) -> Option<AnalysisSession> {
    AnalysisSession::start(request, catalog)
}
