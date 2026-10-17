use sqlbuild_model_config::config_presence::models::MacroPath;

use crate::model_files::models::{HeaderFacts, NativeColumn};
use crate::model_files::tests::helpers::parsed_header_facts;
use crate::model_files::tests::test_types::{ColumnSummary, HeaderFactsTestCase};

fn column_summary(
    column: &NativeColumn,
) -> (
    String,
    Option<String>,
    Option<bool>,
    Option<String>,
    Vec<String>,
) {
    (
        column.name.clone(),
        column.column_type.clone(),
        column.nullable,
        column.description.clone(),
        column
            .audits
            .iter()
            .map(|audit| audit.definition_name.clone())
            .collect(),
    )
}

fn expected_summary(
    column: &ColumnSummary,
) -> (
    String,
    Option<String>,
    Option<bool>,
    Option<String>,
    Vec<String>,
) {
    let (name, column_type, nullable, description, audits) = column;
    (
        (*name).to_owned(),
        column_type.map(str::to_owned),
        *nullable,
        description.map(str::to_owned),
        audits.iter().map(|audit| (*audit).to_owned()).collect(),
    )
}

#[test]
fn given_model_headers_when_reading_native_facts_then_they_match_the_python_projection() {
    let test_cases = [
        HeaderFactsTestCase {
            description: "plain columns parse with their audits and block nothing",
            contents: "MODEL (\n  description 'Orders',\n  materialized table,\n  columns (\n    id (type INTEGER, nullable false, audits [not_null, accepted_values (values [1, 2])]),\n    amount (type DOUBLE, description 'Order amount'),\n  ),\n);\nSELECT 1 AS id, 2.0 AS amount",
            expected_entries: vec![
                ("description", false, None, false),
                ("materialized", false, None, false),
                ("columns", false, None, false),
            ],
            expected_columns: Some(vec![
                (
                    "id",
                    Some("INTEGER"),
                    Some(false),
                    None,
                    vec!["not_null", "accepted_values"],
                ),
                ("amount", Some("DOUBLE"), None, Some("Order amount"), vec![]),
            ]),
        },
        HeaderFactsTestCase {
            description: "templates and macro calls are found per entry with their path",
            contents: "MODEL (\n  description '${env.ORDERS}',\n  columns (\n    id (description '@cents(id)'),\n  ),\n);\nSELECT 1 AS id",
            expected_entries: vec![
                ("description", true, None, true),
                (
                    "columns",
                    false,
                    Some(vec!["columns", "id", "description"]),
                    true,
                ),
            ],
            expected_columns: Some(vec![("id", None, None, Some("@cents(id)"), vec![])]),
        },
        HeaderFactsTestCase {
            description: "columns that fail to parse leave the Python parse to raise the error",
            contents: "MODEL (\n  columns (\n    id (type INTEGER),\n    ID (type INTEGER),\n  ),\n);\nSELECT 1 AS id",
            expected_entries: vec![("columns", false, None, false)],
            expected_columns: None,
        },
        HeaderFactsTestCase {
            description: "a nullable column audited not_null is a parse error",
            contents: "MODEL (\n  columns (\n    id (nullable true, audits [not_null]),\n  ),\n);\nSELECT 1 AS id",
            expected_entries: vec![("columns", false, None, false)],
            expected_columns: None,
        },
    ];
    for test_case in test_cases {
        let facts: HeaderFacts = parsed_header_facts(test_case.contents);
        let entries: Vec<(&str, bool, Option<Vec<&str>>, bool)> = facts
            .entries
            .iter()
            .map(|(key, entry)| {
                (
                    key.as_str(),
                    entry.template,
                    match &entry.macro_path {
                        MacroPath::Found(path) => Some(path.iter().map(String::as_str).collect()),
                        MacroPath::Absent => None,
                    },
                    entry.blocks_reuse,
                )
            })
            .collect();
        assert_eq!(
            entries, test_case.expected_entries,
            "{}",
            test_case.description
        );
        assert_eq!(
            facts
                .columns
                .as_ref()
                .map(|columns| columns.iter().map(column_summary).collect::<Vec<_>>()),
            test_case
                .expected_columns
                .as_ref()
                .map(|columns| columns.iter().map(expected_summary).collect::<Vec<_>>()),
            "{}",
            test_case.description
        );
    }
}
