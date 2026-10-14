//! Planner identity type aliases.

use crate::planner_identity::models::GraphKey;

/// Identity hashes in first-recorded order.
pub type IdentityHashes = Vec<(GraphKey, Option<String>)>;
