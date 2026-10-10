use crate::compiled_project::main::header_column_blocker::header_column_blocker;
use crate::compiled_project::main::plain_model_blocker::plain_model_blocker;
use crate::compiled_project::models::{
    AnalysisOverride, DescriptionShape, PlainModelBlocker, PlainModelCheck,
};
use crate::compiled_project::tests::helpers::{column, plain_check};
use crate::compiled_project::tests::test_types::{HeaderColumnTestCase, PlainBlockerTestCase};

#[test]
fn given_model_check_when_classifying_then_only_plain_models_stay_native() {
    let test_cases = [
        PlainBlockerTestCase {
            description: "description and tags are plain",
            check: PlainModelCheck {
                description: DescriptionShape::Text("Orders.".to_owned()),
                ..plain_check("SELECT 1", &["description", "tags"])
            },
            expected_blocker: None,
        },
        PlainBlockerTestCase {
            description: "failed interpolation",
            check: PlainModelCheck {
                interpolated_sql: None,
                ..plain_check("", &[])
            },
            expected_blocker: Some(PlainModelBlocker::Interpolation),
        },
        PlainBlockerTestCase {
            description: "hooks are finished natively",
            check: plain_check("SELECT 1", &["pre_hooks", "post_hooks"]),
            expected_blocker: None,
        },
        PlainBlockerTestCase {
            description: "declared columns and audits are attached natively",
            check: plain_check("SELECT 1", &["columns", "audits"]),
            expected_blocker: None,
        },
        PlainBlockerTestCase {
            description: "dynamic columns",
            check: plain_check("SELECT 1", &["dynamic_columns"]),
            expected_blocker: Some(PlainModelBlocker::HeaderMetadata),
        },
        PlainBlockerTestCase {
            description: "blank description",
            check: PlainModelCheck {
                description: DescriptionShape::Invalid,
                ..plain_check("SELECT 1", &["description"])
            },
            expected_blocker: Some(PlainModelBlocker::HeaderMetadata),
        },
        PlainBlockerTestCase {
            description: "analysis opted out",
            check: PlainModelCheck {
                analysis_override: AnalysisOverride::Disabled,
                ..plain_check("SELECT 1", &["sql_analysis"])
            },
            expected_blocker: Some(PlainModelBlocker::SqlAnalysisDisabled),
        },
        PlainBlockerTestCase {
            description: "declaration scan stopped",
            check: PlainModelCheck {
                declaration_scan_failed: true,
                ..plain_check("SELECT 1", &[])
            },
            expected_blocker: Some(PlainModelBlocker::DeclarationScan),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            plain_model_blocker(&test_case.check),
            test_case.expected_blocker,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_header_columns_when_classifying_then_enum_types_and_migrations_need_the_attachment() {
    let test_cases = [
        HeaderColumnTestCase {
            description: "typed columns",
            columns: vec![column(Some("INTEGER"), false)],
            expected_blocker: None,
        },
        HeaderColumnTestCase {
            description: "enum-typed column",
            columns: vec![column(Some("order_status"), false)],
            expected_blocker: Some(PlainModelBlocker::EnumColumns),
        },
        HeaderColumnTestCase {
            description: "column migration",
            columns: vec![column(None, true)],
            expected_blocker: Some(PlainModelBlocker::ColumnMigrations),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            header_column_blocker(&test_case.columns, &["order_status".to_owned()]),
            test_case.expected_blocker,
            "{}",
            test_case.description
        );
    }
}
