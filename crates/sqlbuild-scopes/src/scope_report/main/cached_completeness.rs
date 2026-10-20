//! The completeness sections of a cached index.

use crate::scope_report::models::Completeness;

/// The six completeness sections as the report engine reads them.
#[must_use]
pub fn cached_completeness(done: [bool; 6]) -> Completeness {
    Completeness {
        discovery: done[0],
        static_visibility: done[1],
        runtime_usage: done[2],
        relationships: done[3],
        placement: done[4],
        promotion_impact: done[5],
    }
}
