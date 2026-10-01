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
            description: "unquoted word case is ignored",
            dialect: DialectType::Snowflake,
            left: "select count(*) from orders",
            right: "SELECT COUNT(*) FROM ORDERS",
            expected_equal: true,
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
        let left = canonical_tokens(test_case.left, &dialect)?;
        let right = canonical_tokens(test_case.right, &dialect)?;
        assert_eq!(
            left == right,
            test_case.expected_equal,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
