use crate::json::models::JsonValue;
use crate::query_command::main::render_dag_summary::render_dag_summary;
use crate::query_command::main::render_query_json::render_query_json;
use crate::query_command::main::render_query_text::render_query_text;
use crate::query_command::models::{QueryDisplay, QueryLayout};
use crate::query_command::tests::helpers::{invocations, texts};
use crate::query_command::tests::test_types::{
    DagTestCase, DisplayTestCase, FooterTestCase, JsonTestCase,
};

#[test]
fn given_rows_when_rendering_text_then_a_fitting_result_is_boxed_and_others_are_records() {
    let test_cases = [
        DisplayTestCase {
            description: "a narrow result is boxed with types and right-aligned numbers",
            display: invocations(),
            layout: QueryLayout::Fitted { width: 120 },
            expected_text: "┌───────────┬─────────────┬─────────────┐\n\
                            │  status   │   origin    │ invocations │\n\
                            │  varchar  │   varchar   │    int32    │\n\
                            ├───────────┼─────────────┼─────────────┤\n\
                            │ completed │ integration │         133 │\n\
                            │ cancelled │ local       │        NULL │\n\
                            └───────────┴─────────────┴─────────────┘\n\n2 rows\n",
        },
        DisplayTestCase {
            description: "a result wider than the limit prints every value as records",
            display: invocations(),
            layout: QueryLayout::Fitted { width: 40 },
            expected_text: "-[ RECORD 1 ]---------------------------+\nstatus      | completed\n\
                            origin      | integration\ninvocations | 133\n\n\
                            -[ RECORD 2 ]---------------------------+\nstatus      | cancelled\n\
                            origin      | local\ninvocations | NULL\n\n2 rows\n",
        },
        DisplayTestCase {
            description: "a value spanning lines prints as records, and the limit is named",
            display: QueryDisplay {
                columns: texts(&["sql"]),
                rows: vec![texts(&["SELECT 1\nFROM orders"])],
                truncated: true,
                limit: Some(1),
                ..QueryDisplay::default()
            },
            layout: QueryLayout::Fitted { width: 120 },
            expected_text: "-[ RECORD 1 ]---------------------------+\nsql | SELECT 1\nFROM orders\n\n\
                            1 row shown (limit 1; use --limit or --no-limit)\n",
        },
        DisplayTestCase {
            description: "no rows still show the columns, without a type line when none is known",
            display: QueryDisplay {
                columns: texts(&["order_id"]),
                ..QueryDisplay::default()
            },
            layout: QueryLayout::Fitted { width: 120 },
            expected_text: "┌──────────┐\n│ order_id │\n├──────────┤\n└──────────┘\n\n0 rows\n",
        },
        DisplayTestCase {
            description: "the long layout is kept when forced",
            display: QueryDisplay {
                columns: texts(&["id"]),
                rows: vec![texts(&["1"])],
                ..QueryDisplay::default()
            },
            layout: QueryLayout::Long,
            expected_text: "-[ RECORD 1 ]---------------------------+\nid | 1\n\n1 row\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_query_text(&test_case.display, test_case.layout),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_many_rows_when_rendering_text_then_only_more_than_fifty_suggest_aggregating() {
    let test_cases = [
        FooterTestCase {
            description: "fifty rows print only the count",
            row_count: 50,
            expected_footer: "\n50 rows\n",
        },
        FooterTestCase {
            description: "more than fifty rows suggest aggregating",
            row_count: 51,
            expected_footer: "\n51 rows; to read fewer, aggregate with GROUP BY or add a LIMIT\n",
        },
    ];

    for test_case in test_cases {
        let display = QueryDisplay {
            columns: texts(&["n"]),
            rows: (0..test_case.row_count).map(|_| texts(&["7"])).collect(),
            ..QueryDisplay::default()
        };

        let rendered: String = render_query_text(&display, QueryLayout::Fitted { width: 120 });

        assert!(
            rendered.ends_with(test_case.expected_footer),
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
