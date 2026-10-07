use crate::sql_references::main::extract_sql_references::extract_sql_references;
use crate::sql_references::models::ReferenceExtraction;
use crate::sql_references::tests::helpers::{
    backslash_hash_comments, dbt_reference, extracted, failed, generic, reference, table_function,
    unsupported_comments,
};
use crate::sql_references::tests::test_types::ExtractSqlReferencesTestCase;

#[test]
fn given_sql_when_extracting_references_then_matches_python_scanner() {
    let test_cases = [
        ExtractSqlReferencesTestCase {
            description: "every kind in authored order",
            sql: "SELECT * FROM __ref(orders) JOIN __source('raw_orders') JOIN __seed(\"regions\") \
                  JOIN __dbt_ref('shop', customers) WHERE __udf(clean)(x) > 0",
            syntax: generic(),
            expected_extraction: extracted(vec![
                reference("ref", "orders"),
                reference("source", "raw_orders"),
                reference("seed", "regions"),
                dbt_reference("shop", "customers"),
                reference("udf", "clean"),
            ]),
        },
        ExtractSqlReferencesTestCase {
            description: "table function counts top-level call arguments",
            sql: "SELECT * FROM __table_fn(\"expand_orders\") ( 1, f(2, 3), 'a,b' /* , */ )",
            syntax: generic(),
            expected_extraction: extracted(vec![table_function("expand_orders", 3)]),
        },
        ExtractSqlReferencesTestCase {
            description: "table function without call arguments",
            sql: "SELECT * FROM __table_fn(\"daily_orders\")()",
            syntax: generic(),
            expected_extraction: extracted(vec![table_function("daily_orders", 0)]),
        },
        ExtractSqlReferencesTestCase {
            description: "references inside table function arguments are scanned",
            sql: "SELECT * FROM __table_fn(\"f\")((SELECT id FROM __ref(\"orders\")))",
            syntax: generic(),
            expected_extraction: extracted(vec![
                table_function("f", 1),
                reference("ref", "orders"),
            ]),
        },
        ExtractSqlReferencesTestCase {
            description: "comments become spaces inside quoted names",
            sql: "SELECT * FROM __ref(\"a\" /* note */ \"b\")",
            syntax: generic(),
            expected_extraction: extracted(vec![reference("ref", "a\"   \"b")]),
        },
        ExtractSqlReferencesTestCase {
            description: "comments, strings and dollar quotes hide references",
            sql: "-- __ref(a)\nSELECT '__ref(b)', $$__ref(c)$$, /* __ref(d) */ 1 FROM __ref(e)",
            syntax: generic(),
            expected_extraction: extracted(vec![reference("ref", "e")]),
        },
        ExtractSqlReferencesTestCase {
            description: "dialect hash comments hide references",
            sql: "SELECT 1 # __ref(a)\nFROM __ref(b)",
            syntax: backslash_hash_comments(),
            expected_extraction: extracted(vec![reference("ref", "b")]),
        },
        ExtractSqlReferencesTestCase {
            description: "dialect backslash escapes keep strings open",
            sql: "SELECT 'it\\'s __ref(a)' FROM __ref(b)",
            syntax: backslash_hash_comments(),
            expected_extraction: extracted(vec![reference("ref", "b")]),
        },
        ExtractSqlReferencesTestCase {
            description: "non-ascii quoted names are exact",
            sql: "SELECT * FROM __ref(\"commandes_é\")",
            syntax: generic(),
            expected_extraction: extracted(vec![reference("ref", "commandes_é")]),
        },
        ExtractSqlReferencesTestCase {
            description: "wrong reference argument count",
            sql: "SELECT * FROM __ref(a, b)",
            syntax: generic(),
            expected_extraction: failed("__ref must contain exactly one name argument"),
        },
        ExtractSqlReferencesTestCase {
            description: "wrong dbt reference argument count",
            sql: "SELECT * FROM __dbt_ref(a, b, c)",
            syntax: generic(),
            expected_extraction: failed(
                "__dbt_ref must contain one name argument or package/name arguments",
            ),
        },
        ExtractSqlReferencesTestCase {
            description: "empty reference argument",
            sql: "SELECT * FROM __source(a, )",
            syntax: generic(),
            expected_extraction: failed("SQL reference contains an empty argument"),
        },
        ExtractSqlReferencesTestCase {
            description: "empty table function call argument",
            sql: "SELECT * FROM __table_fn(\"f\")(1,,2)",
            syntax: generic(),
            expected_extraction: failed("SQL reference contains an empty argument"),
        },
        ExtractSqlReferencesTestCase {
            description: "table function without call suffix",
            sql: "SELECT * FROM __table_fn(\"f\") /* x */ (1)",
            syntax: generic(),
            expected_extraction: failed("__table_fn must be followed by an argument list"),
        },
        ExtractSqlReferencesTestCase {
            description: "table function call suffix checked before the name",
            sql: "SELECT * FROM __table_fn(f)",
            syntax: generic(),
            expected_extraction: failed("__table_fn must be followed by an argument list"),
        },
        ExtractSqlReferencesTestCase {
            description: "single quoted table function name",
            sql: "SELECT * FROM __table_fn('f')(1)",
            syntax: generic(),
            expected_extraction: failed("__table_fn name argument must be double quoted"),
        },
        ExtractSqlReferencesTestCase {
            description: "unclosed table function call",
            sql: "SELECT * FROM __table_fn(\"f\")(1",
            syntax: generic(),
            expected_extraction: failed("SQL table function call contains an unclosed parenthesis"),
        },
        ExtractSqlReferencesTestCase {
            description: "unclosed reference",
            sql: "SELECT * FROM __ref(orders",
            syntax: generic(),
            expected_extraction: failed("SQL reference contains an unclosed parenthesis"),
        },
        ExtractSqlReferencesTestCase {
            description: "unclosed quoted text",
            sql: "SELECT 'orders",
            syntax: generic(),
            expected_extraction: failed("SQL reference contains an unclosed quoted string"),
        },
        ExtractSqlReferencesTestCase {
            description: "invalid identifier name",
            sql: "SELECT * FROM __ref(1orders)",
            syntax: generic(),
            expected_extraction: failed(
                "__ref name argument must be a quoted string or identifier",
            ),
        },
        ExtractSqlReferencesTestCase {
            description: "nested reference is not a name",
            sql: "SELECT * FROM __ref(__ref(a))",
            syntax: generic(),
            expected_extraction: failed(
                "__ref name argument must be a quoted string or identifier",
            ),
        },
        ExtractSqlReferencesTestCase {
            description: "non-ascii identifier defers",
            sql: "SELECT * FROM __ref(commandés)",
            syntax: generic(),
            expected_extraction: ReferenceExtraction::Deferred,
        },
        ExtractSqlReferencesTestCase {
            description: "non-ascii whitespace before a call suffix defers",
            sql: "SELECT * FROM __table_fn(\"f\")\u{a0}(1)",
            syntax: generic(),
            expected_extraction: ReferenceExtraction::Deferred,
        },
        ExtractSqlReferencesTestCase {
            description: "python whitespace includes ascii separators",
            sql: "SELECT * FROM __table_fn(\"f\")\x1c(1)",
            syntax: generic(),
            expected_extraction: extracted(vec![table_function("f", 1)]),
        },
        ExtractSqlReferencesTestCase {
            description: "unsupported line comment prefix defers",
            sql: "SELECT * FROM __ref(a)",
            syntax: unsupported_comments(),
            expected_extraction: ReferenceExtraction::Deferred,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            extract_sql_references(test_case.sql, &test_case.syntax),
            test_case.expected_extraction,
            "{}",
            test_case.description
        );
    }
}
