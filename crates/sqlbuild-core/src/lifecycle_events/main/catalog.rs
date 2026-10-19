//! `catalog`: the catalogued event definitions of one schema version, in declaration order.

use crate::lifecycle_events::constants::{LIFECYCLE_EVENT_CATALOG_V1, LIFECYCLE_EVENT_CATALOG_V2};
use crate::lifecycle_events::models::EventDefinition;

/// Every definition of `schema_version`, or `None` for an uncatalogued version.
#[must_use]
pub fn catalog(schema_version: i64) -> Option<Vec<EventDefinition>> {
    let entries: &[EventDefinition] = match schema_version {
        1 => &LIFECYCLE_EVENT_CATALOG_V1,
        2 => &LIFECYCLE_EVENT_CATALOG_V2,
        _ => return None,
    };
    Some(entries.to_vec())
}
