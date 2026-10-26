use crate::contracts::main::enum_literal_violations::enum_literal_violations;
use crate::contracts::models::{EnumLiteralModel, EnumLiteralViolation};
use crate::contracts::tests::helpers::{ENUM_HEADER, enum_violation_line, status_column};
use crate::contracts::tests::test_types::{
    EnumLiteralDialectTestCase, EnumLiteralMessageTestCase, EnumLiteralTestCase,
};

#[test]
fn given_enum_column_when_checking_literals_then_reports_non_members() {
    let test_cases = [
        EnumLiteralTestCase {
            description: "a literal written directly as the column",
            authored: "MODEL (description 'Orders');\nSELECT 1 AS order_id, 'pending' AS status\n",
            expanded: None,
            expected_lines: &["status pending 2:23"],
        },
        EnumLiteralTestCase {
            description: "a member literal is accepted",
            authored: "MODEL (description 'Orders');\nSELECT 1 AS order_id, 'open' AS status\n",
            expanded: None,
            expected_lines: &[],
        },
        EnumLiteralTestCase {
            description: "every UNION ALL branch, matched by position",
            authored: "MODEL (description 'Orders');\nSELECT 'open' AS status, 1 AS order_id\nUNION ALL\nSELECT 'pending', 2\nUNION ALL\nSELECT 'void' AS other, 3\n",
            expanded: None,
            expected_lines: &["status pending 4:8", "status void 6:8"],
        },
        EnumLiteralTestCase {
            description: "a literal passed through CTEs and a derived table",
            authored: "MODEL (description 'Orders');\nWITH raw AS (SELECT 'pending' AS status),\nrenamed AS (SELECT r.status FROM raw AS r)\nSELECT status FROM (SELECT * FROM renamed) AS d\n",
            expanded: None,
            expected_lines: &["status pending 2:21"],
        },
        EnumLiteralTestCase {
            description: "a union inside a CTE read through a star",
            authored: "MODEL (description 'Orders');\nWITH unioned AS (\n  SELECT 'open' AS status FROM a\n  UNION ALL\n  SELECT 'held' AS status FROM b\n)\nSELECT * FROM unioned\n",
            expanded: None,
            expected_lines: &["status held 5:10"],
        },
        EnumLiteralTestCase {
            description: "a repeated value is reported once",
            authored: "MODEL (description 'Orders');\nSELECT 'held' AS status\nUNION ALL\nSELECT 'held'\n",
            expanded: None,
            expected_lines: &["status held 2:8"],
        },
        EnumLiteralTestCase {
            description: "computed values are left to the audit",
            authored: "MODEL (description 'Orders');\nWITH raw AS (SELECT LOWER('PENDING') AS status, 'x' AS code)\nSELECT CASE WHEN code = 'x' THEN 'held' ELSE status END AS status FROM raw\n",
            expanded: None,
            expected_lines: &[],
        },
        EnumLiteralTestCase {
            description: "an ambiguous unqualified read across a join is not followed",
            authored: "MODEL (description 'Orders');\nWITH a AS (SELECT 'held' AS status), b AS (SELECT 1 AS id)\nSELECT status FROM a CROSS JOIN b\n",
            expanded: None,
            expected_lines: &[],
        },
        EnumLiteralTestCase {
            description: "an EXCEPT may remove the literal's rows",
            authored: "MODEL (description 'Orders');\nSELECT 'held' AS status\nEXCEPT\nSELECT 'held'\n",
            expanded: None,
            expected_lines: &[],
        },
        EnumLiteralTestCase {
            description: "a filter on the passed-through column may remove the literal's rows",
            authored: "MODEL (description 'Orders');\nWITH a AS (\n  SELECT 1 AS order_id, 'open' AS status\n  UNION ALL\n  SELECT 2, 'other'\n)\nSELECT order_id, status FROM a WHERE status <> 'other'\n",
            expanded: None,
            expected_lines: &[],
        },
        EnumLiteralTestCase {
            description: "a filter on another column may remove the literal's rows",
            authored: "MODEL (description 'Orders');\nWITH a AS (SELECT 2 AS order_id, 'other' AS status)\nSELECT * FROM a WHERE order_id <> 2\n",
            expanded: None,
            expected_lines: &[],
        },
        EnumLiteralTestCase {
            description: "a HAVING or QUALIFY on the reading select stops the passthrough",
            authored: "MODEL (description 'Orders');\nWITH a AS (SELECT 'other' AS status)\nSELECT status FROM a GROUP BY status HAVING COUNT(*) > 1\nUNION ALL\nSELECT status FROM a QUALIFY ROW_NUMBER() OVER (ORDER BY status) > 1\n",
            expanded: None,
            expected_lines: &[],
        },
        EnumLiteralTestCase {
            description: "an inner join may remove the passed-through rows",
            authored: "MODEL (description 'Orders');\nWITH a AS (SELECT 1 AS id, 'other' AS status), b AS (SELECT 2 AS id)\nSELECT a.status FROM a JOIN b ON a.id = b.id\n",
            expanded: None,
            expected_lines: &[],
        },
        EnumLiteralTestCase {
            description: "a limited select may drop the literal's rows",
            authored: "MODEL (description 'Orders');\nSELECT status FROM (SELECT 'other' AS status LIMIT 0) AS d\n",
            expanded: None,
            expected_lines: &[],
        },
        EnumLiteralTestCase {
            description: "a position reaching a by-name union stops the walk",
            authored: "MODEL (description 'Orders');\nSELECT 'open' AS status, 'x' AS note\nUNION ALL\n(SELECT 'held' AS note, 'open' AS status UNION ALL BY NAME SELECT 'open' AS status, 'held' AS note)\n",
            expanded: None,
            expected_lines: &[],
        },
        EnumLiteralTestCase {
            description: "the location is the projected literal, not an earlier comparison",
            authored: "MODEL (description 'Orders');\nWITH f AS (SELECT * FROM t WHERE note = 'held')\nSELECT 'held' AS status FROM f\n",
            expanded: None,
            expected_lines: &["status held 3:8"],
        },
        EnumLiteralTestCase {
            description: "a literal produced by expansion is reported without a location",
            authored: "MODEL (description 'Orders');\nSELECT @py.status() AS status\n",
            expanded: Some("SELECT 'held' AS status\n"),
            expected_lines: &["status held -"],
        },
        EnumLiteralTestCase {
            description: "a query that does not parse has no violations",
            authored: "MODEL (description 'Orders');\nSELECT 'held' AS status FROM (\n",
            expanded: None,
            expected_lines: &[],
        },
    ];

    for test_case in test_cases {
        let query: &str = test_case
            .authored
            .strip_prefix(ENUM_HEADER)
            .expect("authored file starts with the header");
        let model = EnumLiteralModel {
            name: "orders",
            dialect: "duckdb",
            query_sql: test_case.expanded.unwrap_or(query),
            authored_sql: test_case.authored,
            authored_query_sql: query,
            columns: vec![status_column()],
        };

        let lines: Vec<String> = enum_literal_violations(&model)
            .iter()
            .map(enum_violation_line)
            .collect();

        assert_eq!(lines, test_case.expected_lines, "{}", test_case.description);
    }
}

#[test]
fn given_non_member_literal_when_checking_then_message_names_value_model_and_enum() {
    let test_cases = [EnumLiteralMessageTestCase {
        description: "a non-member literal",
        query: "SELECT 'pending' AS status",
        expected_violations: &[(
            "K013",
            "value 'pending' in column 'status' of model 'orders' is not a member of enum order_status",
            "add 'pending' to enum order_status or use one of its members: 'open', 'closed'",
        )],
    }];

    for test_case in test_cases {
        let authored: String = format!("{ENUM_HEADER}{}", test_case.query);
        let model = EnumLiteralModel {
            name: "orders",
            dialect: "duckdb",
            query_sql: test_case.query,
            authored_sql: &authored,
            authored_query_sql: test_case.query,
            columns: vec![status_column()],
        };

        let violations: Vec<EnumLiteralViolation> = enum_literal_violations(&model);

        assert_eq!(
            violations
                .iter()
                .map(|violation| (
                    violation.code,
                    violation.message.as_str(),
                    violation.help.as_str()
                ))
                .collect::<Vec<_>>(),
            test_case.expected_violations,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_case_insensitive_dialect_when_checking_literals_then_skips_the_check() {
    let test_cases = [
        EnumLiteralDialectTestCase {
            description: "SQL Server compares strings ignoring case and trailing spaces",
            dialect: "tsql",
            expected_count: 0,
        },
        EnumLiteralDialectTestCase {
            description: "DuckDB compares strings exactly",
            dialect: "duckdb",
            expected_count: 1,
        },
    ];

    for test_case in test_cases {
        let query: &str = "SELECT 'Open' AS status";
        let authored: String = format!("{ENUM_HEADER}{query}");
        let model = EnumLiteralModel {
            name: "orders",
            dialect: test_case.dialect,
            query_sql: query,
            authored_sql: &authored,
            authored_query_sql: query,
            columns: vec![status_column()],
        };

        assert_eq!(
            enum_literal_violations(&model).len(),
            test_case.expected_count,
            "{}",
            test_case.description
        );
    }
}
