use crate::schema::constants::RECALL_SCHEMA_VERSION;
use crate::schema::main::schema_age::schema_age;
use crate::schema::main::version_plan::version_plan;
use crate::schema::main::view_columns::view_columns;
use crate::schema::models::{SchemaAge, StoreVersion, VersionPlan};
use crate::schema::tests::helpers::{changed_statements_view, current_views};
use crate::schema::tests::test_types::{SchemaAgeTestCase, VersionPlanTestCase};

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
            description: "an unknown column is newer, even beside a missing one",
            observed: changed_statements_view(&["rows_scanned"], &["invocation_started_at"]),
            expected_age: SchemaAge::Newer,
        },
    ];

    let expected = view_columns().expect("this build's views can be listed");
    for test_case in test_cases {
        assert_eq!(
            schema_age(&expected, &test_case.observed),
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
            },
            expected_plan: VersionPlan {
                replace_views: true,
                record: Some(RECALL_SCHEMA_VERSION),
            },
        },
        VersionPlanTestCase {
            description: "a fresh current row needs nothing",
            store: StoreVersion::Recorded {
                version: RECALL_SCHEMA_VERSION,
                age_seconds: DAY,
            },
            expected_plan: VersionPlan {
                replace_views: false,
                record: None,
            },
        },
        VersionPlanTestCase {
            description: "a newer row past half the retention is re-recorded at its version",
            store: StoreVersion::Recorded {
                version: RECALL_SCHEMA_VERSION + 1,
                age_seconds: 16 * DAY,
            },
            expected_plan: VersionPlan {
                replace_views: false,
                record: Some(RECALL_SCHEMA_VERSION + 1),
            },
        },
        VersionPlanTestCase {
            description: "an expired row over older views upgrades",
            store: StoreVersion::Unrecorded(SchemaAge::Older),
            expected_plan: VersionPlan {
                replace_views: true,
                record: Some(RECALL_SCHEMA_VERSION),
            },
        },
        VersionPlanTestCase {
            description: "an expired row over current views only records the version",
            store: StoreVersion::Unrecorded(SchemaAge::Current),
            expected_plan: VersionPlan {
                replace_views: false,
                record: Some(RECALL_SCHEMA_VERSION),
            },
        },
        VersionPlanTestCase {
            description: "an expired row over newer views changes nothing",
            store: StoreVersion::Unrecorded(SchemaAge::Newer),
            expected_plan: VersionPlan {
                replace_views: false,
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
