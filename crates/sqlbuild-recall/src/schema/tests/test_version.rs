use std::collections::BTreeMap;

use crate::schema::_helpers::clickhouse_views::clickhouse_view_bodies;
use crate::schema::constants::{RECALL_SCHEMA_VERSION, VIEW_NAMES};
use crate::schema::main::schema_age::schema_age;
use crate::schema::main::version_plan::version_plan;
use crate::schema::main::view_columns::view_columns;
use crate::schema::models::{SchemaAge, StoreVersion, VersionPlan};
use crate::schema::tests::helpers::{
    changed_statements_view, clickhouse_view_columns, current_views, options,
};
use crate::schema::tests::test_types::{
    SchemaAgeTestCase, VersionPlanTestCase, ViewColumnsTestCase,
};

const RETENTION_DAYS: u32 = 30;
const DAY: i64 = 86_400;

#[test]
fn given_stored_view_columns_when_compared_then_the_store_is_older_current_or_newer() {
    let mut missing_view = current_views();
    missing_view.remove("invocations");
    let test_cases = [
        SchemaAgeTestCase {
            description: "this build's columns are current",
            observed: current_views(),
            expected_age: SchemaAge::Current,
        },
        SchemaAgeTestCase {
            description: "a view lacking a column is older",
            observed: changed_statements_view(&[], &["invocation_started_at"]),
            expected_age: SchemaAge::Older,
        },
        SchemaAgeTestCase {
            description: "a missing view is older",
            observed: missing_view,
            expected_age: SchemaAge::Older,
        },
        SchemaAgeTestCase {
            description: "a user who sees no view cannot judge the store",
            observed: BTreeMap::new(),
            expected_age: SchemaAge::Unseen,
        },
        SchemaAgeTestCase {
            description: "an unknown column is newer, even beside a missing one",
            observed: changed_statements_view(&["rows_scanned"], &["invocation_started_at"]),
            expected_age: SchemaAge::Newer,
        },
    ];

    let expected = view_columns().expect("this build's views can be listed");
    for test_case in test_cases {
        assert_eq!(
            schema_age(&expected, &test_case.observed, &VIEW_NAMES),
            test_case.expected_age,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_store_version_when_planned_then_views_never_downgrade_and_the_row_stays_alive() {
    let test_cases = [
        VersionPlanTestCase {
            description: "an older recorded version upgrades",
            store: StoreVersion::Recorded {
                version: RECALL_SCHEMA_VERSION - 1,
                age_seconds: 0,
                views_visible: true,
            },
            expected_plan: VersionPlan {
                replace_views: true,
                view_ddl: true,
                record: Some(RECALL_SCHEMA_VERSION),
            },
        },
        VersionPlanTestCase {
            description: "a fresh current row needs nothing",
            store: StoreVersion::Recorded {
                version: RECALL_SCHEMA_VERSION,
                age_seconds: DAY,
                views_visible: true,
            },
            expected_plan: VersionPlan {
                replace_views: false,
                view_ddl: true,
                record: None,
            },
        },
        VersionPlanTestCase {
            description: "a newer row past half the retention is re-recorded at its version",
            store: StoreVersion::Recorded {
                version: RECALL_SCHEMA_VERSION + 1,
                age_seconds: 16 * DAY,
                views_visible: true,
            },
            expected_plan: VersionPlan {
                replace_views: false,
                view_ddl: true,
                record: Some(RECALL_SCHEMA_VERSION + 1),
            },
        },
        VersionPlanTestCase {
            description: "an expired row over older views upgrades",
            store: StoreVersion::Unrecorded(SchemaAge::Older),
            expected_plan: VersionPlan {
                replace_views: true,
                view_ddl: true,
                record: Some(RECALL_SCHEMA_VERSION),
            },
        },
        VersionPlanTestCase {
            description: "an expired row over current views only records the version",
            store: StoreVersion::Unrecorded(SchemaAge::Current),
            expected_plan: VersionPlan {
                replace_views: false,
                view_ddl: true,
                record: Some(RECALL_SCHEMA_VERSION),
            },
        },
        VersionPlanTestCase {
            description: "an expired row over newer views changes nothing",
            store: StoreVersion::Unrecorded(SchemaAge::Newer),
            expected_plan: VersionPlan {
                replace_views: false,
                view_ddl: true,
                record: None,
            },
        },
        VersionPlanTestCase {
            description: "a user who sees no view and finds no version row does nothing",
            store: StoreVersion::Unrecorded(SchemaAge::Unseen),
            expected_plan: VersionPlan {
                replace_views: false,
                view_ddl: false,
                record: None,
            },
        },
        VersionPlanTestCase {
            description: "a user who sees no view only refreshes an aging current row",
            store: StoreVersion::Recorded {
                version: RECALL_SCHEMA_VERSION,
                age_seconds: 16 * DAY,
                views_visible: false,
            },
            expected_plan: VersionPlan {
                replace_views: false,
                view_ddl: false,
                record: Some(RECALL_SCHEMA_VERSION),
            },
        },
        VersionPlanTestCase {
            description: "a user who sees no view never records over an older row",
            store: StoreVersion::Recorded {
                version: RECALL_SCHEMA_VERSION - 1,
                age_seconds: 16 * DAY,
                views_visible: false,
            },
            expected_plan: VersionPlan {
                replace_views: false,
                view_ddl: false,
                record: None,
            },
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            version_plan(test_case.store, RETENTION_DAYS),
            test_case.expected_plan,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_each_view_when_both_dialects_are_built_then_they_expose_the_same_columns() {
    let test_cases = [
        ViewColumnsTestCase {
            description: "invocations exposes the same columns in both dialects",
            view: "invocations",
            expected_same: true,
        },
        ViewColumnsTestCase {
            description: "statements exposes the same columns in both dialects",
            view: "statements",
            expected_same: true,
        },
        ViewColumnsTestCase {
            description: "audit_results exposes the same columns in both dialects",
            view: "audit_results",
            expected_same: true,
        },
        ViewColumnsTestCase {
            description: "output_invocations exposes the same columns in both dialects",
            view: "output_invocations",
            expected_same: true,
        },
        ViewColumnsTestCase {
            description: "output_tail exposes the same columns in both dialects",
            view: "output_tail",
            expected_same: true,
        },
        ViewColumnsTestCase {
            description: "output_transcripts exposes the same columns in both dialects",
            view: "output_transcripts",
            expected_same: true,
        },
        ViewColumnsTestCase {
            description: "events exposes the same columns in both dialects",
            view: "events",
            expected_same: true,
        },
        ViewColumnsTestCase {
            description: "diagnostics exposes the same columns in both dialects",
            view: "diagnostics",
            expected_same: true,
        },
        ViewColumnsTestCase {
            description: "artifacts exposes the same columns in both dialects",
            view: "artifacts",
            expected_same: true,
        },
        ViewColumnsTestCase {
            description: "conflicts exposes the same columns in both dialects",
            view: "conflicts",
            expected_same: true,
        },
    ];

    let sqlite = view_columns().expect("this build's views can be listed");
    let bodies: BTreeMap<&str, String> =
        clickhouse_view_bodies(&options(None)).into_iter().collect();
    for test_case in test_cases {
        let clickhouse = clickhouse_view_columns(
            test_case.view,
            bodies.get(test_case.view).map_or("", String::as_str),
        );
        let expected = sqlite.get(test_case.view).cloned().unwrap_or_default();
        assert_eq!(
            clickhouse == expected && !expected.is_empty(),
            test_case.expected_same,
            "{}: ClickHouse {clickhouse:?}, SQLite {expected:?}",
            test_case.description
        );
    }
}
