//! Read one declaration collection once per discovery session and keep it for later stages.

use crate::declaration_files::models::{
    CollectionRequest, DeclarationCollection, DiscoverySession, RetainedCollection,
};
use std::sync::{Arc, MutexGuard, PoisonError};

/// The collection `request` names, read with `discover` the first time the session asks for it.
pub fn retained_collection(
    session: &DiscoverySession,
    request: CollectionRequest,
    discover: impl FnOnce() -> DeclarationCollection,
) -> Arc<DeclarationCollection> {
    if let Some(retained) = collections(session)
        .iter()
        .find(|retained| retained.request == request)
    {
        return Arc::clone(&retained.collection);
    }
    let collection: Arc<DeclarationCollection> = Arc::new(discover());
    collections(session).push(RetainedCollection {
        request,
        collection: Arc::clone(&collection),
    });
    collection
}

/// The session's collections; a panic while another thread held them leaves them readable.
fn collections(session: &DiscoverySession) -> MutexGuard<'_, Vec<RetainedCollection>> {
    session
        .collections
        .lock()
        .unwrap_or_else(PoisonError::into_inner)
}
