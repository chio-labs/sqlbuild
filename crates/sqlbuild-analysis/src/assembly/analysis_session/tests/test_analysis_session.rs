use crate::assembly::analysis_session::main::start_analysis_session::start_analysis_session;
use crate::assembly::analysis_session::tests::helpers::{
    catalog, model_requests, orders_request, session_lines,
};
use crate::assembly::analysis_session::tests::test_types::{SessionTestCase, UnscheduledTestCase};

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
            description: "an unknown column is a binding diagnostic and an untyped output defers",
            models: &[(
                "orders_bad",
                "SELECT missing_column FROM __source(\"raw_orders\")",
                &["raw_orders"],
                &[],
            )],
            expected_steps: &[&["defer enrichment 0"], &[]],
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
                &["defer enrichment 0"],
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
