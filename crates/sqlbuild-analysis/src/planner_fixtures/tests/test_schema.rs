use crate::planner_fixtures::main::{
    fixture_schema::fixture_schema, requires_analysis::requires_analysis,
    unknown_columns::unknown_columns,
};
use crate::planner_fixtures::models::FixtureColumn;
use crate::planner_fixtures::tests::{
    helpers::column,
    test_types::{ExpectedTypesTestCase, SchemaTestCase},
};

#[test]
fn given_closed_and_open_schemas_when_selecting_then_names_and_diagnostics_agree() {
    let test_cases = [
        SchemaTestCase {
            description: "closed complete",
            authoritative: true,
            supplied: &["order_id", "status"],
            expected_analysis: false,
            expected_diagnostic: None,
        },
        SchemaTestCase {
            description: "closed incomplete",
            authoritative: true,
            supplied: &["order_id"],
            expected_analysis: true,
            expected_diagnostic: None,
        },
        SchemaTestCase {
            description: "closed unknown preserves duplicates",
            authoritative: true,
            supplied: &["z_extra", "a_extra", "a_extra"],
            expected_analysis: true,
            expected_diagnostic: Some(
                "mock source 'orders' supplies unknown columns: a_extra, a_extra, z_extra",
            ),
        },
        SchemaTestCase {
            description: "open complete",
            authoritative: false,
            supplied: &["order_id", "status"],
            expected_analysis: true,
            expected_diagnostic: None,
        },
        SchemaTestCase {
            description: "open unknown",
            authoritative: false,
            supplied: &["extra"],
            expected_analysis: true,
            expected_diagnostic: None,
        },
    ];
    for test_case in test_cases {
        let schema = fixture_schema(
            &[
                column("order_id", "INTEGER", false),
                column("status", "VARCHAR", true),
            ],
            test_case.authoritative,
        );
        let supplied: Vec<_> = test_case
            .supplied
            .iter()
            .map(|name| column(name, "INTEGER", true))
            .collect();
        assert_eq!(
            requires_analysis(&supplied, schema.authoritative_names.as_ref()),
            test_case.expected_analysis,
            "{}",
            test_case.description
        );
        assert_eq!(
            unknown_columns(
                "mock source 'orders'",
                &supplied,
                schema.authoritative_names.as_ref()
            )
            .as_deref(),
            test_case.expected_diagnostic,
            "{}",
            test_case.description
        );
        assert_eq!(
            schema.expected_types,
            vec![
                ("order_id".into(), "INTEGER".into()),
                ("status".into(), "VARCHAR".into())
            ],
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_duplicate_folded_columns_when_collecting_types_then_last_declared_type_wins() {
    let test_cases = [
        ExpectedTypesTestCase {
            description: "distinct columns keep declaration order",
            columns: &[
                ("order_id", "order_id", "INTEGER"),
                ("status", "status", "VARCHAR"),
            ],
            expected_types: &[("order_id", "INTEGER"), ("status", "VARCHAR")],
        },
        ExpectedTypesTestCase {
            description: "case variants keep the first position and the last type",
            columns: &[
                ("order_id", "order_id", "INTEGER"),
                ("status", "status", "INTEGER"),
                ("STATUS", "status", "VARCHAR"),
            ],
            expected_types: &[("order_id", "INTEGER"), ("status", "VARCHAR")],
        },
    ];
    for test_case in test_cases {
        let columns: Vec<FixtureColumn> = test_case
            .columns
            .iter()
            .map(|(name, folded_name, sql_type)| FixtureColumn {
                name: (*name).into(),
                folded_name: (*folded_name).into(),
                sql_type: Some((*sql_type).into()),
                nullable: Some(true),
            })
            .collect();
        let schema = fixture_schema(&columns, false);
        let collected: Vec<(&str, &str)> = schema
            .expected_types
            .iter()
            .map(|(name, sql_type)| (name.as_str(), sql_type.as_str()))
            .collect();
        assert_eq!(
            collected.as_slice(),
            test_case.expected_types,
            "{}",
            test_case.description
        );
    }
}
