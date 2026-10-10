//! Give a native model analysis session a per-model analysis cache.

use sqlbuild_cache::store::models::NativeStore;

use crate::assembly::analysis_session::models::AnalysisSession;

/// Read finished outcomes from `store`, whose environment names the build, and add new ones.
pub fn attach_analysis_cache(session: &mut AnalysisSession, store: NativeStore) {
    session.attach_cache(store);
}
