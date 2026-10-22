use std::collections::BTreeMap;

use crate::schema::_helpers::clickhouse_views::clickhouse_view_bodies;
use crate::schema::constants::{RECALL_SCHEMA_VERSION, VIEW_NAMES};
use crate::schema::main::create_database_statement::create_database_statement;
use crate::schema::main::schema_age::schema_age;
use crate::schema::main::store_version_with_views::store_version_with_views;
use crate::schema::main::version_plan::version_plan;
use crate::schema::main::view_columns::view_columns;
use crate::schema::main::view_statements::view_statements;
use crate::schema::models::{DdlOptions, Dialect, SchemaAge, StoreVersion, VersionPlan};
use crate::schema::tests::helpers::{
    changed_statements_view, clickhouse_view_columns, current_views, options,
};
use crate::schema::tests::test_types::{
    CreateDatabaseTestCase, SchemaAgeTestCase, VersionPlanTestCase, ViewColumnsTestCase,
    ViewDefinitionsTestCase,
};

const RETENTION_DAYS: u32 = 30;
const DAY: i64 = 86_400;
const PREVIOUS_VIEW: &str =
    "CREATE VIEW observability.statements AS SELECT 1 AS x SETTINGS join_use_nulls = 1";
const CURRENT_VIEW: &str = "CREATE VIEW observability.statements AS SELECT 1 AS x";

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

#[test]
fn given_view_definitions_when_versioned_then_views_an_older_version_wrote_make_the_store_older() {
    let recorded = |version: i64| StoreVersion::Recorded {
        version,
        age_seconds: DAY,
        views_visible: true,
    };
    let test_cases = [
        ViewDefinitionsTestCase {
            description: "previous views with no version row are older, though columns match",
            store: StoreVersion::Unrecorded(SchemaAge::Current),
            definitions: vec![CURRENT_VIEW.to_owned(), PREVIOUS_VIEW.to_owned()],
            expected_store: StoreVersion::Unrecorded(SchemaAge::Older),
        },
        ViewDefinitionsTestCase {
            description: "previous views recorded as current count as the previous version",
            store: recorded(RECALL_SCHEMA_VERSION),
            definitions: vec![PREVIOUS_VIEW.to_owned()],
            expected_store: recorded(RECALL_SCHEMA_VERSION - 1),
        },
        ViewDefinitionsTestCase {
            description: "current views keep the recorded version",
            store: recorded(RECALL_SCHEMA_VERSION),
            definitions: vec![CURRENT_VIEW.to_owned()],
            expected_store: recorded(RECALL_SCHEMA_VERSION),
        },
        ViewDefinitionsTestCase {
            description: "current views with no version row stay current",
            store: StoreVersion::Unrecorded(SchemaAge::Current),
            definitions: vec![CURRENT_VIEW.to_owned()],
            expected_store: StoreVersion::Unrecorded(SchemaAge::Current),
        },
        ViewDefinitionsTestCase {
            description: "this build's own ClickHouse views keep the current version",
            store: recorded(RECALL_SCHEMA_VERSION),
            definitions: view_statements(Dialect::ClickHouse, &options(None))
                .into_iter()
                .map(|(_, statement)| statement)
                .collect(),
            expected_store: recorded(RECALL_SCHEMA_VERSION),
        },
        ViewDefinitionsTestCase {
            description: "a store recorded by a newer build is never made older",
            store: recorded(RECALL_SCHEMA_VERSION + 1),
            definitions: vec![PREVIOUS_VIEW.to_owned()],
            expected_store: recorded(RECALL_SCHEMA_VERSION + 1),
        },
        ViewDefinitionsTestCase {
            description: "views with columns of a newer build are never made older",
            store: StoreVersion::Unrecorded(SchemaAge::Newer),
            definitions: vec![PREVIOUS_VIEW.to_owned()],
            expected_store: StoreVersion::Unrecorded(SchemaAge::Newer),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            store_version_with_views(
                test_case.store,
                &test_case
                    .definitions
                    .iter()
                    .map(String::as_str)
                    .collect::<Vec<&str>>()
            ),
            test_case.expected_store,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_configured_database_when_rendered_then_it_is_created_only_if_missing() {
    let test_cases = [
        CreateDatabaseTestCase {
            description: "a single server creates the database if it is missing",
            options: options(None),
            expected_statement: Some("CREATE DATABASE IF NOT EXISTS `observability`"),
        },
        CreateDatabaseTestCase {
            description: "a cluster creates it on every node",
            options: options(Some("main")),
            expected_statement: Some(
                "CREATE DATABASE IF NOT EXISTS `observability` ON CLUSTER `main`",
            ),
        },
        CreateDatabaseTestCase {
            description: "no configured database needs no statement",
            options: DdlOptions {
                database: None,
                ..options(None)
            },
            expected_statement: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            create_database_statement(&test_case.options).as_deref(),
            test_case.expected_statement,
            "{}",
            test_case.description
        );
    }
}
