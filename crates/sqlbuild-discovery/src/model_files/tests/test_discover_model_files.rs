use crate::model_files::tests::helpers::{failed, parsed, parsed_summary};
use crate::model_files::tests::test_types::ModelFileTestCase;

const SUPPORTED_KEYS_HELP: &str = "supported keys: audits, columns, constants, description, enums, materialized, tags, unique_key";

#[test]
fn given_model_files_when_parsing_then_values_locations_and_failures_match_python() {
    let test_cases = [
        ModelFileTestCase {
            description: "columns and simple projections",
            contents: "MODEL (\n  columns (\n    id (type INT),\n  ),\n);\nSELECT o.id, total AS amount, sum(x) s FROM t",
            expected_summary: parsed(
                "SELECT o.id, total AS amount, sum(x) s FROM t",
                &[("id", (3, 5, 3, 7))],
                &[
                    ("id", (6, 8, 6, 12)),
                    ("amount", (6, 14, 6, 29)),
                    ("s", (6, 31, 6, 39)),
                ],
            ),
        },
        ModelFileTestCase {
            description: "non-ASCII before the header shifts code-point columns",
            contents: "MODEL (description 'é', columns (id (type INT)));\nSELECT \"Ünit\" FROM t",
            expected_summary: parsed(
                "SELECT \"Ünit\" FROM t",
                &[("id", (1, 34, 1, 36))],
                &[("Ünit", (2, 8, 2, 14))],
            ),
        },
        ModelFileTestCase {
            description: "a UNION hides the projection list",
            contents: "MODEL ();\nSELECT a FROM t UNION ALL SELECT a FROM u",
            expected_summary: parsed("SELECT a FROM t UNION ALL SELECT a FROM u", &[], &[]),
        },
        ModelFileTestCase {
            description: "dotless i spells UNION for Python's upper()",
            contents: "MODEL ();\nSELECT a FROM t unıon SELECT a FROM u",
            expected_summary: parsed(
                "SELECT a FROM t unıon SELECT a FROM u",
                &[],
                &[("a", (2, 8, 2, 9))],
            ),
        },
        ModelFileTestCase {
            description: "missing header",
            contents: "SELECT 1",
            expected_summary: failed(
                "SQL model '/project/models/orders.sql' must start with a MODEL(...) header as the first non-whitespace content",
                None,
            ),
        },
        ModelFileTestCase {
            description: "byte order mark is not whitespace",
            contents: "\u{feff}MODEL ();\nSELECT 1",
            expected_summary: failed(
                "SQL model '/project/models/orders.sql' must start with a MODEL(...) header as the first non-whitespace content",
                None,
            ),
        },
        ModelFileTestCase {
            description: "header syntax",
            contents: "MODEL (materialized: table);\nSELECT 1",
            expected_summary: failed(
                "MODEL(...) in '/project/models/orders.sql' contains invalid SQLBuild header syntax: unexpected ':' after key 'materialized'; use SQLBuild syntax 'materialized value'",
                None,
            ),
        },
        ModelFileTestCase {
            description: "removed key",
            contents: "MODEL (run_despite_unchanged true, bogus 1);\nSELECT 1",
            expected_summary: failed(
                "MODEL() option(s) run_despite_unchanged in '/project/models/orders.sql' were removed with virtual environments; projects run in direct mode",
                None,
            ),
        },
        ModelFileTestCase {
            description: "unsupported key on a later line with a suggestion",
            contents: "MODEL (\n  materialized table,\n  /* note */ tagz [a],\n);\nSELECT 1",
            expected_summary: failed(
                "MODEL() in '/project/models/orders.sql:3' has unsupported keys: tagz",
                Some("did you mean 'tags'?"),
            ),
        },
        ModelFileTestCase {
            description: "unsupported key after a line comment",
            contents: "MODEL (materialized table, -- c\n  col_x 1);\nSELECT 1",
            expected_summary: failed(
                "MODEL() in '/project/models/orders.sql:2' has unsupported keys: col_x",
                Some(SUPPORTED_KEYS_HELP),
            ),
        },
        ModelFileTestCase {
            description: "two unsupported keys without suggestions",
            contents: "MODEL (zzz 1, qqq 2);\nSELECT 1",
            expected_summary: failed(
                "MODEL() in '/project/models/orders.sql:1' has unsupported keys: zzz, qqq",
                Some(SUPPORTED_KEYS_HELP),
            ),
        },
        ModelFileTestCase {
            description: "empty query",
            contents: "MODEL ();\n  \n",
            expected_summary: failed(
                "SQL model '/project/models/orders.sql' must contain SQL after MODEL(...)",
                None,
            ),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            parsed_summary(test_case.contents),
            test_case.expected_summary,
            "{}",
            test_case.description
        );
    }
}
