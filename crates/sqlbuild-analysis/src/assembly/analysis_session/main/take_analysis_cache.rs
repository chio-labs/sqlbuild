//! Take a session's analysis cache back to save it.

use sqlbuild_cache::store::models::NativeStore;

use crate::assembly::analysis_session::models::{AnalysisCacheStats, AnalysisSession};

/// The attached store with this session's outcomes, and its hit, miss and store counts.
pub fn take_analysis_cache(
    session: &mut AnalysisSession,
) -> Option<(NativeStore, AnalysisCacheStats)> {
    session.take_cache()
}
