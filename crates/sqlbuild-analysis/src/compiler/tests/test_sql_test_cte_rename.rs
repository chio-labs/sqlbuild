use crate::compiler::_helpers::sql_tests::cte_rename::{CteRename, defined_cte_keys, rename_ctes};
use crate::compiler::_helpers::sql_tests::cte_slices::{SliceDialect, split_top_level_with};
use crate::compiler::tests::test_types::{CteRenameTestCase, DefinedCteKeysTestCase};

#[test]
fn given_tsql_cte_when_renaming_by_token_span_then_only_relation_references_change() {
    let test_cases = [
        CteRenameTestCase {
            description: "definition, FROM reference and qualifier are renamed",
            sql: "WITH final AS (SELECT 1 AS id) SELECT final.id FROM final",
            renamed_index: 0,
            expected_sql: Some(
                "WITH __sqb_cte_0 AS (SELECT 1 AS id) SELECT __sqb_cte_0.id FROM __sqb_cte_0",
            ),
        },
        CteRenameTestCase {
            description: "references in later CTEs, subqueries and joins are renamed",
            sql: "WITH final AS (SELECT 1 AS id), other AS (SELECT id FROM (SELECT id FROM final) AS s \
                  WHERE id IN (SELECT id FROM final)) SELECT * FROM other JOIN final ON final.id = other.id",
            renamed_index: 0,
            expected_sql: Some(
                "WITH __sqb_cte_0 AS (SELECT 1 AS id), other AS (SELECT id FROM (SELECT id FROM __sqb_cte_0) AS s \
                 WHERE id IN (SELECT id FROM __sqb_cte_0)) SELECT * FROM other JOIN __sqb_cte_0 ON __sqb_cte_0.id = other.id",
            ),
        },
        CteRenameTestCase {
            description: "bracketed and case-variant references are renamed",
            sql: "WITH [Final] AS (SELECT 1 AS id) SELECT FINAL.id FROM [final] JOIN Final AS f ON f.id = FINAL.id",
            renamed_index: 0,
            expected_sql: Some(
                "WITH __sqb_cte_0 AS (SELECT 1 AS id) SELECT __sqb_cte_0.id FROM __sqb_cte_0 \
                 JOIN __sqb_cte_0 AS f ON f.id = __sqb_cte_0.id",
            ),
        },
        CteRenameTestCase {
            description: "qualified columns, comments and strings named like the CTE are kept",
            sql: "WITH final AS (SELECT t.final, 'final' AS label FROM dbo.final AS t) -- final\n\
                  SELECT final.final FROM final",
            renamed_index: 0,
            expected_sql: Some(
                "WITH __sqb_cte_0 AS (SELECT t.final, 'final' AS label FROM dbo.final AS t) -- final\n\
                 SELECT __sqb_cte_0.final FROM __sqb_cte_0",
            ),
        },
        CteRenameTestCase {
            description: "a database named like the CTE in a three-part name is kept",
            sql: "WITH final AS (SELECT 1 AS id) SELECT f.id FROM final f \
                  JOIN final.dbo.orders o ON o.id = f.id",
            renamed_index: 0,
            expected_sql: Some(
                "WITH __sqb_cte_0 AS (SELECT 1 AS id) SELECT f.id FROM __sqb_cte_0 f \
                 JOIN final.dbo.orders o ON o.id = f.id",
            ),
        },
        CteRenameTestCase {
            description: "a schema named like the CTE in a two-part name is kept",
            sql: "WITH final AS (SELECT 1 AS id) SELECT f.id FROM final.orders o JOIN final f ON f.id = o.id",
            renamed_index: 0,
            expected_sql: Some(
                "WITH __sqb_cte_0 AS (SELECT 1 AS id) SELECT f.id FROM final.orders o \
                 JOIN __sqb_cte_0 f ON f.id = o.id",
            ),
        },
        CteRenameTestCase {
            description: "column qualifiers in SELECT and ON are renamed",
            sql: "WITH final AS (SELECT 1 AS id) SELECT final.id FROM final JOIN orders o ON o.id = final.id",
            renamed_index: 0,
            expected_sql: Some(
                "WITH __sqb_cte_0 AS (SELECT 1 AS id) SELECT __sqb_cte_0.id FROM __sqb_cte_0 \
                 JOIN orders o ON o.id = __sqb_cte_0.id",
            ),
        },
        CteRenameTestCase {
            description: "a qualifier beside a multipart object of the same name is ambiguous",
            sql: "WITH final AS (SELECT 1 AS id) SELECT final.id FROM final.orders",
            renamed_index: 0,
            expected_sql: None,
        },
        CteRenameTestCase {
            description: "an unqualified column alias named like the CTE is ambiguous",
            sql: "WITH final AS (SELECT 1 AS id) SELECT id AS final FROM final",
            renamed_index: 0,
            expected_sql: None,
        },
        CteRenameTestCase {
            description: "a reference before the definition is ambiguous",
            sql: "WITH a AS (SELECT * FROM final), final AS (SELECT 1 AS id) SELECT * FROM a, final",
            renamed_index: 1,
            expected_sql: None,
        },
    ];

    for test_case in test_cases {
        let dialect = SliceDialect::new(Some("tsql"));
        let split = split_top_level_with(test_case.sql, dialect)
            .expect("balanced SQL")
            .expect("leading WITH");
        let actual = rename_ctes(
            test_case.sql,
            &split,
            &[CteRename {
                index: test_case.renamed_index,
                name: "__sqb_cte_0",
            }],
            dialect,
        );
        assert_eq!(
            actual.as_deref(),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_statement_when_listing_defined_ctes_then_only_with_list_entries_count() {
    let test_cases = [
        DefinedCteKeysTestCase {
            description: "top-level and nested WITH lists are listed",
            sql: "WITH base AS (SELECT 1 AS id), other AS (WITH inner_rows AS (SELECT id FROM base) \
                  SELECT id FROM inner_rows) SELECT id FROM other",
            expected_keys: &["base", "other", "inner_rows"],
        },
        DefinedCteKeysTestCase {
            description: "named windows are not CTEs",
            sql: "SELECT order_id, row_number() OVER w1 AS n FROM orders \
                  WINDOW w1 AS (ORDER BY order_id), base AS (PARTITION BY order_id)",
            expected_keys: &[],
        },
        DefinedCteKeysTestCase {
            description: "a WITH list after a named window in a subquery is still listed",
            sql: "SELECT * FROM (SELECT id FROM t WINDOW w AS (ORDER BY id), v AS (ORDER BY id)) AS s \
                  JOIN (WITH base AS (SELECT 1 AS id), rows_two AS (SELECT 2 AS id) SELECT id FROM base) AS b \
                  ON b.id = s.id",
            expected_keys: &["base", "rows_two"],
        },
    ];
    for test_case in test_cases {
        let keys =
            defined_cte_keys(test_case.sql, SliceDialect::new(Some("duckdb"))).expect("scans");
        assert_eq!(keys, test_case.expected_keys, "{}", test_case.description);
    }
}
