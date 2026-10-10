//! Give a native model analysis session a per-model analysis cache.

use sqlbuild_cache::store::models::NativeStore;

use crate::assembly::analysis_session::models::AnalysisSession;

/// Read finished outcomes from `store` and add this session's; the store's environment must
/// already name the build and every setting outside the session request.
pub fn attach_analysis_cache(session: &mut AnalysisSession, store: NativeStore) {
    session.attach_cache(store);
}
