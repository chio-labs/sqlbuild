//! Discover, read and parse one declaration collection in Python's discovery order.

use crate::_helpers::pool::discovery_pool;
use crate::declaration_files::_helpers::listing::collection_reads::{
    CollectionSource, failed_collection, read_collection,
};
use crate::declaration_files::models::{
    CollectionRequest, DeclarationCollection, DiscoverySession,
};
use crate::models::StageFailure;
use crate::tree::models::ProjectTree;

/// The collection `request` names, every file read and parsed on the discovery pool.
pub fn discover_declaration_collection(
    session: &DiscoverySession,
    tree: &ProjectTree,
    request: CollectionRequest,
) -> DeclarationCollection {
    match discovery_pool() {
        Ok(pool) => pool.install(|| read_collection(&CollectionSource { session, tree }, request)),
        Err(reason) => failed_collection(request.kind, StageFailure::Internal(reason)),
    }
}
