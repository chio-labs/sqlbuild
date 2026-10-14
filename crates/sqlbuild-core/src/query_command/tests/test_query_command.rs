use crate::json::models::JsonValue;
use crate::query_command::main::render_dag_summary::render_dag_summary;
use crate::query_command::main::render_query_csv::render_query_csv;
use crate::query_command::main::render_query_json::render_query_json;
use crate::query_command::main::render_query_long::render_query_long;
use crate::query_command::main::render_query_table::render_query_table;
use crate::query_command::models::QueryDisplay;
use crate::query_command::tests::helpers::texts;
use crate::query_command::tests::test_types::{
    CsvTestCase, DagTestCase, DisplayTestCase, JsonTestCase,
};

#[test]
fn given_rows_when_rendering_text_then_aligns_and_counts() {
    let test_cases = [
        DisplayTestCase {
            description: "two rows with unicode and a truncation hint",
            display: QueryDisplay {
                columns: texts(&["id", "name"]),
                rows: vec![texts(&["1", "héllo"]), texts(&["22", ""])],
                truncated: true,
                limit: Some(2),
            },
            expected_long: "-[ RECORD 1 ]---------------------------+\nid   | 1\nname | héllo\n\n-[ RECORD 2 ]---------------------------+\nid   | 22\nname | \n\n2 rows\nShowing 2 rows. Use --limit to show more or --no-limit to disable the limit.\n",
            expected_table: "id | name \n-- | -----\n1  | héllo\n22 |\n\n2 rows\nShowing 2 rows. Use --limit to show more or --no-limit to disable the limit.\n",
        },
        DisplayTestCase {
            description: "no rows and an unlimited truncation leaves an empty line",
            display: QueryDisplay {
                columns: texts(&["x"]),
                rows: Vec::new(),
                truncated: true,
                limit: None,
            },
            expected_long: "\n0 rows\n\n",
            expected_table: "x\n-\n\n0 rows\n\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_query_long(&test_case.display),
            test_case.expected_long,
            "{}",
            test_case.description
        );
        assert_eq!(
            render_query_table(&test_case.display),
            test_case.expected_table,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_rows_when_rendering_csv_then_quotes_minimally() {
    let test_cases = [CsvTestCase {
        description: "delimiters, quotes, newlines and a lone empty field",
        columns: texts(&["a", "b"]),
        rows: vec![
            texts(&["x,y", "q\"z"]),
            texts(&["l\nm", ""]),
            texts(&[""]),
            Vec::new(),
        ],
        expected_csv: "a,b\n\"x,y\",\"q\"\"z\"\n\"l\nm\",\n\"\"\n\n",
    }];

    for test_case in test_cases {
        assert_eq!(
            render_query_csv(&test_case.columns, &test_case.rows),
            test_case.expected_csv,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_rows_when_rendering_json_then_keeps_first_position_and_last_value() {
    let test_cases = [JsonTestCase {
        description: "a repeated column and non-ASCII text",
        columns: texts(&["a", "b", "a"]),
        rows: vec![vec![
            JsonValue::Bool(true),
            JsonValue::String("é".to_owned()),
            JsonValue::Null,
        ]],
        expected_json: "[{\"a\": null, \"b\": \"\\u00e9\"}]\n",
    }];

    for test_case in test_cases {
        assert_eq!(
            render_query_json(&test_case.columns, test_case.rows).ok(),
            Some(test_case.expected_json.to_owned()),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_graph_counts_when_summarizing_dag_then_reports_them() {
    let test_cases = [DagTestCase {
        description: "nodes, edges and checks",
        counts: (20, 24, 36),
        expected_text: "DAG ready (20 nodes, 24 edges, 36 checks)\n",
    }];

    for test_case in test_cases {
        assert_eq!(
            render_dag_summary(test_case.counts),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
