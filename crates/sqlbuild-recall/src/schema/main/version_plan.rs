//! `version_plan`: whether a writer replaces the views and which version it records.

use crate::schema::constants::{RECALL_SCHEMA_VERSION, SECONDS_PER_DAY};
use crate::schema::models::{SchemaAge, StoreVersion, VersionPlan};

/// Upgrade an older store and record this build's version; never replace a newer store's views or record a lower version than it holds. A version row older than half the retention is appended again with the highest version seen, so retention never removes the last one.
#[must_use]
pub fn version_plan(store: StoreVersion, retention_days: u32) -> VersionPlan {
    match store {
        StoreVersion::Recorded { version, .. } if version < RECALL_SCHEMA_VERSION => VersionPlan {
            replace_views: true,
            record: Some(RECALL_SCHEMA_VERSION),
        },
        StoreVersion::Recorded {
            version,
            age_seconds,
        } => VersionPlan {
            replace_views: false,
            record: (age_seconds.saturating_mul(2) > i64::from(retention_days) * SECONDS_PER_DAY)
                .then_some(version),
        },
        StoreVersion::Unrecorded(SchemaAge::Older) => VersionPlan {
            replace_views: true,
            record: Some(RECALL_SCHEMA_VERSION),
        },
        StoreVersion::Unrecorded(SchemaAge::Current) => VersionPlan {
            replace_views: false,
            record: Some(RECALL_SCHEMA_VERSION),
        },
        StoreVersion::Unrecorded(SchemaAge::Newer) => VersionPlan {
            replace_views: false,
            record: None,
        },
    }
}
