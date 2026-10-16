use crate::state_tables::main::create_table_sql::create_table_sql;
use crate::state_tables::main::values_insert_sql::values_insert_sql;
use crate::state_tables::tests::helpers::column;
use crate::state_tables::tests::test_types::{CreateTableTestCase, ValuesInsertTestCase};

#[test]
fn given_columns_when_rendering_ddl_then_required_columns_are_not_null() {
    let test_cases = [
        CreateTableTestCase {
            description: "mixed required columns",
            columns: vec![column("a", "VARCHAR", true), column("b", "BIGINT", false)],
            expected_sql: "CREATE TABLE IF NOT EXISTS s.t (a VARCHAR NOT NULL, b BIGINT)",
        },
        CreateTableTestCase {
            description: "no columns",
            columns: Vec::new(),
            expected_sql: "CREATE TABLE IF NOT EXISTS s.t ()",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            create_table_sql("s.t", &test_case.columns),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_rows_when_rendering_insert_then_each_row_is_one_values_tuple() {
    let test_cases = [ValuesInsertTestCase {
        description: "two rows",
        rows: vec![
            vec!["'a'".to_owned(), "NULL".to_owned()],
            vec!["'b'".to_owned(), "'c'".to_owned()],
        ],
        expected_sql: "INSERT INTO s.t (x, y) VALUES ('a', NULL), ('b', 'c')",
    }];

    for test_case in test_cases {
        assert_eq!(
            values_insert_sql("s.t", &["x", "y"], &test_case.rows),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}
