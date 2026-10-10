use sqlbuild_core::constants::PANIC_MESSAGE;

use crate::lineage::_helpers::rich_lineage::outcomes_in_order;
use crate::lineage::models::RichLineageOutcome;
use crate::lineage::tests::test_types::RichPanicTestCase;

const PANICKING_SQL: &str = "SELECT secret_token FROM orders";
const MANY_MODELS: &[&str] = &[
    "SELECT 0",
    "SELECT 1",
    "SELECT 2",
    "SELECT 3",
    "SELECT 4",
    "SELECT 5",
    "SELECT 6",
    "SELECT 7",
    "SELECT 8",
    "SELECT 9",
    "SELECT 10",
    "SELECT 11",
    "SELECT 12",
    "SELECT 13",
];

/// A panic fails the request with the fixed native error (no SQL, no payload), never a deferral.
#[test]
fn given_an_injected_panic_when_building_rich_lineage_then_the_request_fails() {
    let test_cases = [
        RichPanicTestCase {
            description: "no panic answers every model in request order",
            models: MANY_MODELS,
            expected_outcome: Ok(MANY_MODELS),
        },
        RichPanicTestCase {
            description: "one panicking model fails the request",
            models: &["SELECT 1", PANICKING_SQL, "SELECT 2"],
            expected_outcome: Err(PANIC_MESSAGE),
        },
        RichPanicTestCase {
            description: "several panicking models still fail with the same error",
            models: &[PANICKING_SQL, "SELECT 1", PANICKING_SQL],
            expected_outcome: Err(PANIC_MESSAGE),
        },
    ];
    for test_case in test_cases {
        let models: Vec<String> = test_case
            .models
            .iter()
            .map(|sql| (*sql).to_owned())
            .collect();
        let outcomes = outcomes_in_order(&models, |query_sql| {
            assert_ne!(query_sql, PANICKING_SQL, "injected parser panic");
            RichLineageOutcome::Skipped(query_sql.to_owned())
        });
        let answered: Result<Vec<String>, String> = outcomes.map(|outcomes| {
            outcomes
                .into_iter()
                .map(|outcome| outcome.into_parts().3.unwrap_or_default())
                .collect()
        });
        assert_eq!(
            answered
                .as_ref()
                .map(|sqls| sqls.iter().map(String::as_str).collect::<Vec<&str>>())
                .map_err(String::as_str),
            test_case.expected_outcome.map(<[&str]>::to_vec),
            "{}",
            test_case.description
        );
    }
}
