use polyglot_sql::{Dialect, DialectType};

use crate::sql_tokens::main::canonical_tokens::canonical_tokens;
use crate::sql_tokens::tests::test_types::CanonicalTokensTestCase;

#[test]
fn given_sql_pairs_when_canonicalizing_then_only_layout_comments_and_word_case_are_ignored()
-> Result<(), String> {
    let test_cases = [
        CanonicalTokensTestCase {
            description: "whitespace between tokens is ignored",
            dialect: DialectType::DuckDB,
            left: "select a,b from orders",
            right: "SELECT\n  a, b\nFROM orders",
            expected_equal: true,
        },
        CanonicalTokensTestCase {
            description: "comments are ignored",
            dialect: DialectType::Snowflake,
            left: "select a -- note\nfrom orders /* block */",
            right: "select a from orders",
            expected_equal: true,
        },
        CanonicalTokensTestCase {
            description: "keyword and built-in function case is ignored",
            dialect: DialectType::Snowflake,
            left: "select count(*) from orders",
            right: "SELECT COUNT(*) FROM orders",
            expected_equal: true,
        },
        CanonicalTokensTestCase {
            description: "unquoted identifier case is significant",
            dialect: DialectType::Snowflake,
            left: "select count(*) from orders",
            right: "SELECT COUNT(*) FROM ORDERS",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "Snowflake path key case is significant",
            dialect: DialectType::Snowflake,
            left: "select payload:customerId from t",
            right: "select payload:customerid from t",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "BigQuery qualified table case is significant",
            dialect: DialectType::BigQuery,
            left: "select * from ds.Orders",
            right: "select * from ds.orders",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "DuckDB alias case is significant",
            dialect: DialectType::DuckDB,
            left: "select 1 as Foo",
            right: "select 1 as foo",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "keyword-named qualified name case is significant",
            dialect: DialectType::BigQuery,
            left: "select * from inventory.view",
            right: "select * from inventory.VIEW",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "keyword-named alias case is significant",
            dialect: DialectType::DuckDB,
            left: "select pos as index from t",
            right: "select pos AS INDEX from t",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "user-defined function case is significant",
            dialect: DialectType::DuckDB,
            left: "select my_udf(a) from t",
            right: "select MY_UDF(a) from t",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "built-in function case is ignored",
            dialect: DialectType::DuckDB,
            left: "select coalesce(a, 0) from t",
            right: "select COALESCE(a, 0) from t",
            expected_equal: true,
        },
        CanonicalTokensTestCase {
            description: "Snowflake double-slash comments are ignored",
            dialect: DialectType::Snowflake,
            left: "select a // note\nfrom t",
            right: "select a from t",
            expected_equal: true,
        },
        CanonicalTokensTestCase {
            description: "BigQuery hash comments are ignored",
            dialect: DialectType::BigQuery,
            left: "select a # note\nfrom t",
            right: "select a from t",
            expected_equal: true,
        },
        CanonicalTokensTestCase {
            description: "DuckDB struct-literal key case is significant",
            dialect: DialectType::DuckDB,
            left: "select {Key: 1}",
            right: "select {key: 1}",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "a non-reserved keyword operand before an operator keeps its case",
            dialect: DialectType::DuckDB,
            left: "select a, Rows ^ 2 from t",
            right: "select a, rows ^ 2 from t",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "a non-reserved keyword table in a comma join keeps its case",
            dialect: DialectType::BigQuery,
            left: "select * from ds.a, View v",
            right: "select * from ds.a, view v",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "a reserved word after a dot is a field name",
            dialect: DialectType::BigQuery,
            left: "select abc.Group from abc",
            right: "select abc.group from abc",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "a reserved keyword column alias keeps its case",
            dialect: DialectType::DuckDB,
            left: "select 1 as Select",
            right: "select 1 as select",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "reserved keyword case is ignored",
            dialect: DialectType::DuckDB,
            left: "select a from t where a in (1) limit 1",
            right: "SELECT a FROM t WHERE a IN (1) LIMIT 1",
            expected_equal: true,
        },
        CanonicalTokensTestCase {
            description: "Databricks reserves no keywords",
            dialect: DialectType::Databricks,
            left: "select a from t",
            right: "SELECT a FROM t",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "whitespace inside a string literal is significant",
            dialect: DialectType::DuckDB,
            left: "select 'a  b' as code",
            right: "select 'a b' as code",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "string literal case is significant",
            dialect: DialectType::DuckDB,
            left: "select 'Open' as status",
            right: "select 'OPEN' as status",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "quoted identifier case is significant",
            dialect: DialectType::Snowflake,
            left: "select \"Order\" from orders",
            right: "select \"ORDER\" from orders",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "dollar-quoted literal content is significant",
            dialect: DialectType::PostgreSQL,
            left: "select $$a  b$$ as note",
            right: "select $$a b$$ as note",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "number spelling is significant",
            dialect: DialectType::DuckDB,
            left: "select 1.0 as amount",
            right: "select 1.00 as amount",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "a renamed function is significant",
            dialect: DialectType::Snowflake,
            left: "select startswith(code, 'EU')",
            right: "select starts_with(code, 'EU')",
            expected_equal: false,
        },
        CanonicalTokensTestCase {
            description: "an added alias keyword is significant",
            dialect: DialectType::DuckDB,
            left: "select a b from orders",
            right: "select a as b from orders",
            expected_equal: false,
        },
    ];
    for test_case in test_cases {
        let dialect = Dialect::get(test_case.dialect);
        let left_tokens = dialect
            .tokenize(test_case.left)
            .map_err(|error| error.to_string())?;
        let right_tokens = dialect
            .tokenize(test_case.right)
            .map_err(|error| error.to_string())?;
        let left = canonical_tokens(test_case.left, &left_tokens, &dialect)?;
        let right = canonical_tokens(test_case.right, &right_tokens, &dialect)?;
        assert_eq!(
            left == right,
            test_case.expected_equal,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
