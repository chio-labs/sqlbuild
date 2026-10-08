use crate::test_targets::main::scenario_source_violation::scenario_source_violation;
use crate::test_targets::tests::helpers::cte;
use crate::test_targets::tests::test_types::ScenarioSourceTestCase;

#[test]
fn given_scenario_sources_when_validating_then_python_first_error_is_returned() {
    let test_cases = [
        ScenarioSourceTestCase {
            description: "known sources in fixtures pass",
            ctes: vec![
                cte("__source__raw", false, &["raw"]),
                cte("__expected__orders", true, &[]),
            ],
            expected_error: None,
        },
        ScenarioSourceTestCase {
            description: "a check CTE reading a source is reported before unknown fixture sources",
            ctes: vec![
                cte("helper", false, &["missing"]),
                cte("__expected__orders", true, &["raw"]),
            ],
            expected_error: Some(
                "SQL scenario file tests/scenarios/orders.sql CTE '__expected__orders' must not reference project source 'raw' with __source(); source-backed scenario data is only allowed in helper and fixture CTEs",
            ),
        },
        ScenarioSourceTestCase {
            description: "an unknown source in a helper CTE",
            ctes: vec![cte("helper", false, &["raw", "missing"])],
            expected_error: Some(
                "SQL scenario file tests/scenarios/orders.sql references unknown source 'missing'",
            ),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            scenario_source_violation(
                "tests/scenarios/orders.sql",
                &test_case.ctes,
                &["raw".to_owned()]
            )
            .as_deref(),
            test_case.expected_error,
            "{}",
            test_case.description
        );
    }
}
