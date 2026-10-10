use crate::model_validation::tests::helpers::column_migration_message;
use crate::model_validation::tests::test_types::ColumnMigrationTestCase;

#[test]
fn given_column_renames_when_validating_then_first_problem_is_reported() {
    let test_cases = [
        ColumnMigrationTestCase {
            description: "incremental rename is accepted",
            materialized: Some("incremental"),
            model_migrates: false,
            columns: &[("revenue", Some("amount"))],
            expected_message: None,
        },
        ColumnMigrationTestCase {
            description: "table without its own migrate_from is rebuilt",
            materialized: Some("table"),
            model_migrates: false,
            columns: &[("revenue", Some("amount"))],
            expected_message: Some(
                "model 'orders': column 'revenue' declares migrate_from, which is only valid for \
                 incremental and snapshot models, or for table and view models that declare \
                 migrate_from themselves (the old name's compatibility view then presents the \
                 column under its old name); 'table' models are rebuilt with their new columns",
            ),
        },
        ColumnMigrationTestCase {
            description: "qualified origin",
            materialized: Some("incremental"),
            model_migrates: false,
            columns: &[("revenue", Some("orders.amount"))],
            expected_message: Some(
                "model 'orders': column 'revenue' migrate_from must name one column of the \
                 model's existing table",
            ),
        },
        ColumnMigrationTestCase {
            description: "two columns claim one origin",
            materialized: Some("incremental"),
            model_migrates: false,
            columns: &[("revenue", Some("amount")), ("total", Some("AMOUNT"))],
            expected_message: Some(
                "model 'orders': columns 'revenue' and 'total' both declare migrate_from AMOUNT; \
                 a column can be renamed to only one new name",
            ),
        },
        ColumnMigrationTestCase {
            description: "swapped renames",
            materialized: Some("snapshot"),
            model_migrates: false,
            columns: &[("left_id", Some("right_id")), ("right_id", Some("left_id"))],
            expected_message: Some(
                "model 'orders': column 'left_id' migrates from 'right_id', which itself declares \
                 migrate_from; chained or swapped column renames are not supported",
            ),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            column_migration_message(
                test_case.materialized,
                test_case.model_migrates,
                test_case.columns
            )
            .as_deref(),
            test_case.expected_message,
            "{}",
            test_case.description
        );
    }
}
