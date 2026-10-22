//! `version_plan`: whether a writer replaces the views and which version it records.

use crate::schema::constants::{RECALL_SCHEMA_VERSION, SECONDS_PER_DAY};
use crate::schema::models::{SchemaAge, StoreVersion, VersionPlan};

/// Upgrade an older store and record this build's version; never replace a newer store's views or record a lower version than it holds. A version row older than half the retention is appended again with the highest version seen, so retention never removes the last one. A user who sees no view runs no view statements and, without a version row, records none.
#[must_use]
pub fn version_plan(store: StoreVersion, retention_days: u32) -> VersionPlan {
    let refresh = |version: i64, age_seconds: i64| {
        (age_seconds.saturating_mul(2) > i64::from(retention_days) * SECONDS_PER_DAY)
            .then_some(version)
    };
    let plan = |replace_views: bool, record: Option<i64>| VersionPlan {
        replace_views,
        view_ddl: true,
        record,
    };
    match store {
        StoreVersion::Recorded {
            version,
            age_seconds,
            views_visible: false,
        } => VersionPlan {
            replace_views: false,
            view_ddl: false,
            record: (version >= RECALL_SCHEMA_VERSION)
                .then(|| refresh(version, age_seconds))
                .flatten(),
        },
        StoreVersion::Recorded { version, .. } if version < RECALL_SCHEMA_VERSION => {
            plan(true, Some(RECALL_SCHEMA_VERSION))
        }
        StoreVersion::Recorded {
            version,
            age_seconds,
            ..
        } => plan(false, refresh(version, age_seconds)),
        StoreVersion::Unrecorded(SchemaAge::Older) => plan(true, Some(RECALL_SCHEMA_VERSION)),
        StoreVersion::Unrecorded(SchemaAge::Current) => plan(false, Some(RECALL_SCHEMA_VERSION)),
        StoreVersion::Unrecorded(SchemaAge::Newer) => plan(false, None),
        StoreVersion::Unrecorded(SchemaAge::Unseen) => VersionPlan {
            replace_views: false,
            view_ddl: false,
            record: None,
        },
    }
}
