use crate::type_system::main::normalize_type::normalize_type;
use crate::type_system::tests::helpers::normalization_text;
use crate::type_system::tests::test_types::{BracketDepthTestCase, NormalizeTypeTestCase};

#[test]
fn given_type_strings_when_normalizing_then_python_normalization_is_returned() {
    let test_cases = [
        NormalizeTypeTestCase {
            description: "integer aliases keep their spelling outside Snowflake and BigQuery",
            type_sql: "integer",
            dialect: "duckdb",
            expected_normalization: Some("INT | integer | - | - | - | -"),
        },
        NormalizeTypeTestCase {
            description: "BigQuery integers are INT64",
            type_sql: "INT",
            dialect: "bigquery",
            expected_normalization: Some("INT64 | integer | - | - | - | -"),
        },
        NormalizeTypeTestCase {
            description: "Snowflake integers are DECIMAL(38,0)",
            type_sql: "BIGINT",
            dialect: "snowflake",
            expected_normalization: Some("DECIMAL(38,0) | decimal | 38 | 0 | - | -"),
        },
        NormalizeTypeTestCase {
            description: "Snowflake NUMBER is a custom type rewritten to DECIMAL",
            type_sql: "NUMBER(12, 2)",
            dialect: "snowflake",
            expected_normalization: Some("DECIMAL(12,2) | decimal | 12 | 2 | - | -"),
        },
        NormalizeTypeTestCase {
            description: "Snowflake NUMBER without precision takes the integer default",
            type_sql: "NUMBER",
            dialect: "snowflake",
            expected_normalization: Some("DECIMAL(38,0) | decimal | 38 | 0 | - | -"),
        },
        NormalizeTypeTestCase {
            description: "Snowflake unbounded text takes the default length",
            type_sql: "TEXT",
            dialect: "snowflake",
            expected_normalization: Some("VARCHAR(16777216) | string | - | - | 16777216 | -"),
        },
        NormalizeTypeTestCase {
            description: "Snowflake timestamp aliases",
            type_sql: "TIMESTAMP_NTZ",
            dialect: "snowflake",
            expected_normalization: Some("TIMESTAMP_NTZ | timestamp | - | - | - | -"),
        },
        NormalizeTypeTestCase {
            description: "decimal precision and scale",
            type_sql: "decimal(10, 2)",
            dialect: "duckdb",
            expected_normalization: Some("DECIMAL(10,2) | decimal | 10 | 2 | - | -"),
        },
        NormalizeTypeTestCase {
            description: "nested types are other",
            type_sql: "ARRAY<STRUCT<a INT>>",
            dialect: "bigquery",
            expected_normalization: Some("ARRAY<STRUCT<AINT64>> | other | - | - | - | -"),
        },
        NormalizeTypeTestCase {
            description: "a parse failure falls back to the text and reports the error",
            type_sql: "order status",
            dialect: "generic",
            expected_normalization: Some(
                "ORDERSTATUS | other | - | - | - | Parse error at line 1, column 13: Unexpected token after data type: status",
            ),
        },
        NormalizeTypeTestCase {
            description: "a dialect this build does not include defers",
            type_sql: "INT",
            dialect: "mysql",
            expected_normalization: None,
        },
        NormalizeTypeTestCase {
            description: "a dialect Polyglot does not know defers so Python raises",
            type_sql: "INT",
            dialect: "motherduck",
            expected_normalization: None,
        },
        NormalizeTypeTestCase {
            description: "non-ASCII text defers",
            type_sql: "caf\u{e9}",
            dialect: "generic",
            expected_normalization: None,
        },
        NormalizeTypeTestCase {
            description: "a parameter beyond i64 defers",
            type_sql: "order status(99999999999999999999)",
            dialect: "generic",
            expected_normalization: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            normalize_type(test_case.type_sql, test_case.dialect)
                .as_ref()
                .map(normalization_text)
                .as_deref(),
            test_case.expected_normalization,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_array_suffixes_when_normalizing_on_a_small_stack_then_deep_types_defer() {
    let test_cases = [
        BracketDepthTestCase {
            description: "at the bracket cap, parsed on a 1 MiB debug-build stack",
            depth: 32,
            expected_native: true,
        },
        BracketDepthTestCase {
            description: "one past the bracket cap",
            depth: 33,
            expected_native: false,
        },
        BracketDepthTestCase {
            description: "far past the bracket cap",
            depth: 100_000,
            expected_native: false,
        },
    ];

    for test_case in test_cases {
        let type_sql: String = format!("INT{}", "[]".repeat(test_case.depth));
        let answered: bool = std::thread::Builder::new()
            .stack_size(1024 * 1024)
            .spawn(move || normalize_type(&type_sql, "generic").is_some())
            .expect("the test thread starts")
            .join()
            .expect("normalization does not overflow the stack");
        assert_eq!(
            answered, test_case.expected_native,
            "{}",
            test_case.description
        );
    }
}
