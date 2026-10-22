//! `store_version_with_views`: a ClickHouse store's version, corrected by its view definitions.

use crate::schema::constants::{RECALL_SCHEMA_VERSION, SUPERSEDED_CLICKHOUSE_VIEW_MARKERS};
use crate::schema::models::{SchemaAge, StoreVersion};

/// `store`, made older when a view definition still holds text that only an older schema version wrote: neither a version row nor view columns prove that the views were replaced. A store recorded or judged newer than this build is left alone, so its views are never downgraded.
#[must_use]
pub fn store_version_with_views(store: StoreVersion, view_definitions: &[&str]) -> StoreVersion {
    let Some(views_version) = SUPERSEDED_CLICKHOUSE_VIEW_MARKERS
        .iter()
        .filter(|(marker, _)| holds(view_definitions, marker))
        .map(|(_, version)| *version)
        .min()
    else {
        return store;
    };
    match store {
        StoreVersion::Recorded {
            version,
            age_seconds,
            views_visible,
        } if version > views_version && version <= RECALL_SCHEMA_VERSION => {
            StoreVersion::Recorded {
                version: views_version,
                age_seconds,
                views_visible,
            }
        }
        StoreVersion::Unrecorded(SchemaAge::Current) => StoreVersion::Unrecorded(SchemaAge::Older),
        other => other,
    }
}

fn holds(view_definitions: &[&str], marker: &str) -> bool {
    view_definitions
        .iter()
        .any(|definition| definition.contains(marker))
}
