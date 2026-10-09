use crate::assembly::analysis_session::main::prove_dynamic_contracts::prove_dynamic_contracts;
use crate::assembly::analysis_session::main::prove_finished_dynamic_contracts::prove_finished_dynamic_contracts;
use crate::assembly::analysis_session::main::start_analysis_session::start_analysis_session;
use crate::assembly::analysis_session::models::PivotOutcome;
use crate::assembly::analysis_session::tests::helpers::{
    catalog, fact_lines, failed, finished_session, model_requests, orders_request, pivot_request,
    proven, session_lines,
};
use crate::assembly::analysis_session::tests::test_types::{
    PivotTestCase, SessionFactsTestCase, SessionTestCase, UnscheduledTestCase,
};

#[test]
fn given_models_when_running_the_session_then_defers_and_publishes_as_python_does() {
    let test_cases = [
        SessionTestCase {
            description: "typed producers publish closed shapes their consumers bind",
            models: &[
                (
                    "stg_orders",
                    "SELECT order_id, amount * 2 AS doubled FROM __source(\"raw_orders\")",
                    &["raw_orders"],
                    &[],
                ),
                (
                    "orders_mart",
                    "SELECT doubled, order_id + 1 AS next_id FROM __ref(\"stg_orders\")",
                    &[],
                    &["stg_orders"],
                ),
                (
                    "orders_star",
                    "SELECT * FROM __ref(\"stg_orders\")",
                    &[],
                    &["stg_orders"],
                ),
            ],
            expected_steps: &[&[
                "publish stg_orders order_id:INTEGER doubled:DOUBLE",
                "publish orders_mart doubled:DOUBLE next_id:INT",
                "publish orders_star order_id:INT doubled:DOUBLE",
            ]],
            expected_outcomes: &[
                &[
                    "order_id INTEGER non_null",
                    "doubled DOUBLE unknown",
                    "succeeded=true star=false/true diagnostics=[]",
                ],
                &[
                    "doubled DOUBLE unknown",
                    "next_id INT unknown",
                    "succeeded=true star=false/true diagnostics=[]",
                ],
                &[
                    "order_id INT unknown",
                    "doubled DOUBLE unknown",
                    "succeeded=true star=true/true diagnostics=[]",
                ],
            ],
        },
        SessionTestCase {
            description: "an unknown column is a binding diagnostic and enriches natively",
            models: &[(
                "orders_bad",
                "SELECT missing_column FROM __source(\"raw_orders\")",
                &["raw_orders"],
                &[],
            )],
            expected_steps: &[&[]],
            expected_outcomes: &[&[
                "missing_column - unknown",
                "succeeded=true star=false/false diagnostics=[\"B002\"]",
            ]],
        },
        SessionTestCase {
            description: "an open source's consumers defer to Python",
            models: &[
                (
                    "events",
                    "SELECT event_id FROM __source(\"raw_events\")",
                    &["raw_events"],
                    &[],
                ),
                (
                    "events_mart",
                    "SELECT event_id, 1 AS one FROM __ref(\"events\")",
                    &[],
                    &["events"],
                ),
            ],
            expected_steps: &[
                &["publish events event_id:UNKNOWN", "defer analysis 1"],
                &[],
            ],
            expected_outcomes: &[
                &[
                    "event_id - unknown",
                    "succeeded=true star=false/false diagnostics=[]",
                ],
                &["succeeded=true star=false/false diagnostics=[]"],
            ],
        },
        SessionTestCase {
            description: "a set operation never re-analyses with its inputs",
            models: &[(
                "orders_union",
                "SELECT order_id FROM __source(\"raw_events\") UNION ALL SELECT 1",
                &["raw_events"],
                &[],
            )],
            expected_steps: &[&["publish orders_union order_id:UNKNOWN"]],
            expected_outcomes: &[&[
                "order_id - unknown",
                "succeeded=true star=false/false diagnostics=[]",
            ]],
        },
    ];
    for test_case in test_cases {
        let (steps, outcomes) = session_lines(test_case.models);

        assert_eq!(steps, test_case.expected_steps, "{}", test_case.description);
        assert_eq!(
            outcomes, test_case.expected_outcomes,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_finished_sessions_when_reading_model_facts_then_keeps_only_native_successes() {
    let test_cases = [
        SessionFactsTestCase {
            description: "native lineage keeps output names and sources",
            models: &[
                (
                    "stg_orders",
                    "SELECT order_id, amount * 2 AS doubled FROM __source(\"raw_orders\")",
                    &["raw_orders"],
                    &[],
                ),
                (
                    "orders_bad",
                    "SELECT missing_column FROM __source(\"raw_orders\")",
                    &["raw_orders"],
                    &[],
                ),
            ],
            expected_facts: &[
                "Some([\"order_id\", \"doubled\"]) \
                 order_id<-[(\"raw_orders\", \"order_id\")] \
                 doubled<-[(\"raw_orders\", \"amount\")]",
                "Some([\"missing_column\"]) missing_column<-[(\"raw_orders\", \"missing_column\")]",
            ],
        },
        SessionFactsTestCase {
            description: "a model Python analysed keeps no session facts",
            models: &[
                (
                    "events",
                    "SELECT event_id FROM __source(\"raw_events\")",
                    &["raw_events"],
                    &[],
                ),
                (
                    "events_mart",
                    "SELECT event_id, 1 AS one FROM __ref(\"events\")",
                    &[],
                    &["events"],
                ),
            ],
            expected_facts: &[
                "Some([\"event_id\"]) event_id<-[(\"raw_events\", \"event_id\")]",
                "none",
            ],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            fact_lines(test_case.models),
            test_case.expected_facts,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_unschedulable_models_when_starting_then_python_analyses() {
    let test_cases = [
        UnscheduledTestCase {
            description: "models that reference each other",
            models: &[
                (
                    "orders",
                    "SELECT order_id FROM __ref(\"returns\")",
                    &[],
                    &["returns"],
                ),
                (
                    "returns",
                    "SELECT order_id FROM __ref(\"orders\")",
                    &[],
                    &["orders"],
                ),
            ],
            expected_started: false,
        },
        UnscheduledTestCase {
            description: "two models with one name",
            models: &[
                ("orders", "SELECT 1 AS order_id", &[], &[]),
                ("orders", "SELECT 2 AS order_id", &[], &[]),
            ],
            expected_started: false,
        },
    ];
    for test_case in test_cases {
        let request = orders_request(model_requests(test_case.models));
        let catalog = catalog(&request.dialect, &request.catalog_schemas);

        assert_eq!(
            start_analysis_session(request, &catalog).is_some(),
            test_case.expected_started,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_dynamic_pivots_when_proving_then_matches_python_or_defers() {
    let test_cases = [
        PivotTestCase {
            description: "a bare DuckDB pivot keeps its GROUP BY columns",
            dialect: "duckdb",
            sql: "PIVOT __source(\"raw_orders\") ON status USING MAX(amount) GROUP BY customer_id",
            family: Some(("status", "amount", "MAX")),
            expected_outcome: proven(
                &[("customer_id", "INTEGER", "non_null")],
                Some("DOUBLE"),
                "raw_orders",
                true,
            ),
        },
        PivotTestCase {
            description: "a cast aggregate renders its target type",
            dialect: "duckdb",
            sql: "PIVOT __source(\"raw_orders\") ON status \
                USING MIN(CAST(amount AS DECIMAL(12, 2))) GROUP BY customer_id",
            family: Some(("status", "amount", "MIN")),
            expected_outcome: proven(
                &[("customer_id", "INTEGER", "non_null")],
                Some("DECIMAL(12, 2)"),
                "raw_orders",
                true,
            ),
        },
        PivotTestCase {
            description: "a CTE input without GROUP BY keeps the remaining input columns",
            dialect: "snowflake",
            sql: "WITH base AS (SELECT customer_id, status, amount FROM __source(\"raw_orders\")) \
                SELECT * FROM base PIVOT (SUM(amount) FOR status IN (ANY ORDER BY status))",
            family: Some(("status", "amount", "SUM")),
            expected_outcome: proven(
                &[("customer_id", "INTEGER", "non_null")],
                None,
                "raw_orders",
                false,
            ),
        },
        PivotTestCase {
            description: "a passthrough redeclaring the upstream families",
            dialect: "duckdb",
            sql: "SELECT * FROM __ref(\"status_amounts\")",
            family: Some(("status", "amount", "MAX")),
            expected_outcome: proven(
                &[("customer_id", "INTEGER", "unknown")],
                Some("DOUBLE"),
                "status_amounts",
                false,
            ),
        },
        PivotTestCase {
            description: "static pivot values",
            dialect: "snowflake",
            sql: "SELECT * FROM __source(\"raw_orders\") PIVOT (MAX(amount) FOR status IN ('placed'))",
            family: Some(("status", "amount", "MAX")),
            expected_outcome: failed(
                "static pivot values must use ordinary exact column declarations",
            ),
        },
        PivotTestCase {
            description: "DuckDB values on the ON clause",
            dialect: "duckdb",
            sql: "PIVOT __source(\"raw_orders\") ON status IN ('placed') USING MAX(amount)",
            family: Some(("status", "amount", "MAX")),
            expected_outcome: failed(
                "dynamic column contracts currently require exactly one pivot column",
            ),
        },
        PivotTestCase {
            description: "a dialect without dynamic pivots",
            dialect: "postgres",
            sql: "SELECT 1",
            family: Some(("status", "amount", "MAX")),
            expected_outcome: failed(
                "adapter dialect 'postgres' does not support compiler-proven dynamic pivots",
            ),
        },
        PivotTestCase {
            description: "a declared pivot column the pivot does not use",
            dialect: "duckdb",
            sql: "PIVOT __source(\"raw_orders\") ON status USING MAX(amount) GROUP BY customer_id",
            family: Some(("order_id", "amount", "MAX")),
            expected_outcome: failed(
                "dynamic family 'amounts' declares pivot_column 'order_id' but the output pivot uses 'status'",
            ),
        },
        PivotTestCase {
            description: "SQL Python reports as a parse error",
            dialect: "duckdb",
            sql: "PIVOT FROM WHERE",
            family: Some(("status", "amount", "MAX")),
            expected_outcome: PivotOutcome::Deferred,
        },
        PivotTestCase {
            description: "non-ASCII names Python casefolds differently",
            dialect: "duckdb",
            sql: "SELECT * FROM __ref(\"stra\u{df}e\")",
            family: Some(("status", "amount", "MAX")),
            expected_outcome: PivotOutcome::Deferred,
        },
        PivotTestCase {
            description: "no declared families",
            dialect: "duckdb",
            sql: "SELECT 1",
            family: None,
            expected_outcome: PivotOutcome::Absent,
        },
    ];
    for test_case in test_cases {
        let request = pivot_request(test_case.dialect, test_case.sql, test_case.family);
        let session = finished_session(request.tables.clone());

        let standalone = prove_dynamic_contracts(&request).expect("the proofs run");
        let in_session =
            prove_finished_dynamic_contracts(&session, &request.models).expect("the proofs run");

        assert_eq!(
            standalone,
            vec![test_case.expected_outcome.clone(), PivotOutcome::Absent],
            "{}",
            test_case.description
        );
        assert_eq!(
            in_session,
            vec![test_case.expected_outcome, PivotOutcome::Absent],
            "{}",
            test_case.description
        );
    }
}
