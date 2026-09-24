use crate::compiler::_helpers::sql_references::extraction::extract;
use crate::compiler::_helpers::sql_tests::sql_scan::{self, Unclosed};
use crate::engine::tests::test_types::SqlScannerTestCase;
use crate::rules::_helpers::evaluation::normalize_rules_sql;
use crate::rules::_helpers::numeric_decisions::compact_sql;
use crate::sql_lint::_helpers::preparation::prepare;

#[test]
fn given_quoted_commented_and_malformed_fragments_when_scanning_then_every_scanner_is_characterised()
-> Result<(), String> {
    let test_cases = [
        SqlScannerTestCase {
            description: "plain code",
            fragment: "a",
            expected_compiler_paren: Ok(4),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", a x, 1)",
            expected_table_function_token: "SELECT a __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *               , a FROM t",
            expected_snowflake_comma: "SELECT a a  FROM t",
            expected_compact: "a=aandb",
            expected_lint_site: Some("@m(a x)"),
            expected_reference_fast_path: true,
        },
        SqlScannerTestCase {
            description: "single quote containing open paren",
            fragment: "'a(b'",
            expected_compiler_paren: Ok(8),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", 'a(b' x, 1)",
            expected_table_function_token: "SELECT 'a(b' __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *                   , a FROM t",
            expected_snowflake_comma: "SELECT 'a(b' a  FROM t",
            expected_compact: "a='a(b'andb",
            expected_lint_site: Some("@m('a(b' x)"),
            expected_reference_fast_path: true,
        },
        SqlScannerTestCase {
            description: "single quote containing close paren",
            fragment: "'a)b'",
            expected_compiler_paren: Ok(8),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", 'a)b' x, 1)",
            expected_table_function_token: "SELECT 'a)b' __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *                   , a FROM t",
            expected_snowflake_comma: "SELECT 'a)b' a  FROM t",
            expected_compact: "a='a)b'andb",
            expected_lint_site: Some("@m('a)b' x)"),
            expected_reference_fast_path: true,
        },
        SqlScannerTestCase {
            description: "doubled single quote",
            fragment: "'it''s )'",
            expected_compiler_paren: Ok(12),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", 'it''s )' x, 1)",
            expected_table_function_token: "SELECT 'it''s )' __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *                       , a FROM t",
            expected_snowflake_comma: "SELECT 'it''s )' a  FROM t",
            expected_compact: "a='it''s )'andb",
            expected_lint_site: Some("@m('it''s )' x)"),
            expected_reference_fast_path: true,
        },
        SqlScannerTestCase {
            description: "backslash escaped quote before close paren",
            fragment: "'a\\')'",
            expected_compiler_paren: Ok(5),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", 'a\\')' x)(1)",
            expected_table_function_token: "SELECT 'a\\')' __table_fn(\"o\")(1)",
            expected_snowflake_exclude: "SELECT *               ' x) , a FROM t",
            expected_snowflake_comma: "SELECT 'a\\')' a, FROM t",
            expected_compact: "a='a\\')' and  b",
            expected_lint_site: Some("@m('a\\')' x)"),
            expected_reference_fast_path: false,
        },
        SqlScannerTestCase {
            description: "backslash escaped quote before open paren",
            fragment: "'a\\'('",
            expected_compiler_paren: Err(Unclosed::Quote),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", 'a\\'(' x)(1)",
            expected_table_function_token: "SELECT 'a\\'(' __table_fn(\"o\")(1)",
            expected_snowflake_exclude: "SELECT * EXCLUDE ('a\\'(' x) , a FROM t",
            expected_snowflake_comma: "SELECT 'a\\'(' a, FROM t",
            expected_compact: "a='a\\'(' and  b",
            expected_lint_site: Some("@m('a\\'(' x)"),
            expected_reference_fast_path: false,
        },
        SqlScannerTestCase {
            description: "double quote containing close paren",
            fragment: "\"a)b\"",
            expected_compiler_paren: Ok(8),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", \"a)b\" x, 1)",
            expected_table_function_token: "SELECT \"a)b\" __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *                   , a FROM t",
            expected_snowflake_comma: "SELECT \"a)b\" a  FROM t",
            expected_compact: "a=\"a)b\"andb",
            expected_lint_site: Some("@m(\"a)b\" x)"),
            expected_reference_fast_path: true,
        },
        SqlScannerTestCase {
            description: "backtick containing close paren",
            fragment: "`a)b`",
            expected_compiler_paren: Ok(8),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", `a)b` x)(1)",
            expected_table_function_token: "SELECT `a)b` __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *             b` x) , a FROM t",
            expected_snowflake_comma: "SELECT `a)b` a  FROM t",
            expected_compact: "a=`a)b`andb",
            expected_lint_site: Some("@m(`a)"),
            expected_reference_fast_path: true,
        },
        SqlScannerTestCase {
            description: "doubled backtick",
            fragment: "`a``)b`",
            expected_compiler_paren: Ok(10),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", `a``)b` x)(1)",
            expected_table_function_token: "SELECT `a``)b` __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *               b` x) , a FROM t",
            expected_snowflake_comma: "SELECT `a``)b` a  FROM t",
            expected_compact: "a=`a``)b`andb",
            expected_lint_site: Some("@m(`a``)"),
            expected_reference_fast_path: true,
        },
        SqlScannerTestCase {
            description: "line comment",
            fragment: "-- )\n",
            expected_compiler_paren: Ok(8),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", -- )\n x, 1)",
            expected_table_function_token: "SELECT -- )\n __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *              \n    , a FROM t",
            expected_snowflake_comma: "SELECT -- )\n a  FROM t",
            expected_compact: "a=andb",
            expected_lint_site: Some("@m(-- )\n x)"),
            expected_reference_fast_path: true,
        },
        SqlScannerTestCase {
            description: "block comment",
            fragment: "/* ) */",
            expected_compiler_paren: Ok(10),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", /* ) */ x, 1)",
            expected_table_function_token: "SELECT /* ) */ __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *                     , a FROM t",
            expected_snowflake_comma: "SELECT /* ) */ a  FROM t",
            expected_compact: "a=andb",
            expected_lint_site: Some("@m(/* ) */ x)"),
            expected_reference_fast_path: true,
        },
        SqlScannerTestCase {
            description: "nested block comment",
            fragment: "/* /* ) */ ) */",
            expected_compiler_paren: Ok(12),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", /* /* ) */ ) */ x)(1)",
            expected_table_function_token: "SELECT /* /* ) */ ) */ __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *                       */ x) , a FROM t",
            expected_snowflake_comma: "SELECT /* /* ) */ ) */ a  FROM t",
            expected_compact: "a=)*/andb",
            expected_lint_site: Some("@m(/* /* ) */ )"),
            expected_reference_fast_path: true,
        },
        SqlScannerTestCase {
            description: "dollar quote",
            fragment: "$$ ) $$",
            expected_compiler_paren: Ok(4),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", $$ ) $$ x)(1)",
            expected_table_function_token: "SELECT $$ ) $$ __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *               $$ x) , a FROM t",
            expected_snowflake_comma: "SELECT $$ ) $$ a  FROM t",
            expected_compact: "a=$$)$$andb",
            expected_lint_site: Some("@m($$ )"),
            expected_reference_fast_path: true,
        },
        SqlScannerTestCase {
            description: "unterminated quote",
            fragment: "'abc",
            expected_compiler_paren: Err(Unclosed::Quote),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", 'abc x)(1)",
            expected_table_function_token: "SELECT 'abc __table_fn(\"o\")(1)",
            expected_snowflake_exclude: "SELECT * EXCLUDE ('abc x) , a FROM t",
            expected_snowflake_comma: "SELECT 'abc a, FROM t",
            expected_compact: "a='abc and  b",
            expected_lint_site: Some(""),
            expected_reference_fast_path: false,
        },
        SqlScannerTestCase {
            description: "unterminated block comment",
            fragment: "/* abc",
            expected_compiler_paren: Err(Unclosed::BlockComment),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", /* abc x)(1)",
            expected_table_function_token: "SELECT /* abc __table_fn(\"o\")(1)",
            expected_snowflake_exclude: "SELECT * EXCLUDE (/* abc x) , a FROM t",
            expected_snowflake_comma: "SELECT /* abc a, FROM t",
            expected_compact: "a=",
            expected_lint_site: Some(""),
            expected_reference_fast_path: false,
        },
        SqlScannerTestCase {
            description: "multibyte utf8",
            fragment: "'é)ü' ñ",
            expected_compiler_paren: Ok(13),
            expected_table_function: "SELECT * FROM __table_fn(\"o\", 'é)ü' ñ x, 1)",
            expected_table_function_token: "SELECT 'é)ü' ñ __table_fn(\"o\", 1)",
            expected_snowflake_exclude: "SELECT *                        , a FROM t",
            expected_snowflake_comma: "SELECT 'é)ü' ñ a  FROM t",
            expected_compact: "a='é)ü'ñandb",
            expected_lint_site: None,
            expected_reference_fast_path: true,
        },
    ];

    for test_case in test_cases {
        let fragment = test_case.fragment;
        assert_eq!(
            sql_scan::matching_paren(&format!("({fragment} x) y"), 0),
            test_case.expected_compiler_paren,
            "compiler matching paren: {}",
            test_case.description
        );
        assert_eq!(
            normalize_rules_sql(
                "duckdb",
                &format!("SELECT * FROM __table_fn(\"o\", {fragment} x)(1)")
            ),
            test_case.expected_table_function,
            "rules table-function parenthesis: {}",
            test_case.description
        );
        assert_eq!(
            normalize_rules_sql("duckdb", &format!("SELECT {fragment} __table_fn(\"o\")(1)")),
            test_case.expected_table_function_token,
            "rules table-function token search: {}",
            test_case.description
        );
        assert_eq!(
            normalize_rules_sql(
                "snowflake",
                &format!("SELECT * EXCLUDE ({fragment} x) , a FROM t")
            ),
            test_case.expected_snowflake_exclude,
            "rules Snowflake EXCLUDE parenthesis: {}",
            test_case.description
        );
        assert_eq!(
            normalize_rules_sql("snowflake", &format!("SELECT {fragment} a, FROM t")),
            test_case.expected_snowflake_comma,
            "rules Snowflake trailing comma: {}",
            test_case.description
        );
        assert_eq!(
            compact_sql(&format!("A = {fragment} AND  B")),
            test_case.expected_compact,
            "rules numeric decision compaction: {}",
            test_case.description
        );
        let lint_sql = format!("SELECT @m({fragment} x) AS y");
        let lint_site = prepare(&lint_sql, &lint_sql, &[])?.map(|prepared| {
            prepared
                .1
                .first()
                .map(|site| site.5.clone())
                .unwrap_or_default()
        });
        assert_eq!(
            lint_site.as_deref(),
            test_case.expected_lint_site,
            "SQL lint macro site: {}",
            test_case.description
        );
        assert_eq!(
            extract(&format!("SELECT {fragment} __ref('b')")).is_some(),
            test_case.expected_reference_fast_path,
            "SQL reference fast path: {}",
            test_case.description
        );
    }
    Ok(())
}
