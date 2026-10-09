use crate::semantic_checks::tests::helpers::{completion_summary, described};
use crate::semantic_checks::tests::test_types::CompletionTestCase;

const OPT_OUT_HELP: &str = "remove `sql_analysis false` and fix the findings it was hiding: \
     1 unknown function (run `sqb compile` to see them)\n  = help: to allow `sql_analysis false` \
     on any model, SQL test or audit, set this in sqlbuild_project.toml:\n            \
     [settings]\n            require_sql_analysis = false";
const OPT_OUT_NOTE: &str = "sqlbuild_project.toml sets [settings] require_sql_analysis = true, \
     which only allows `sql_analysis false` on SQL that SQLBuild cannot parse; this model parses \
     successfully.";

#[test]
fn given_failing_project_when_completing_then_recovers_explains_and_rejects_like_python() {
    let test_cases = [
        CompletionTestCase {
            description: "a recovered typo, an explained comparison, a test error and an opt-out",
            non_ascii_comment: false,
            without_diagnostics: false,
            expected_deferral: None,
            expected_diagnostics: vec![
                described(
                    "B002",
                    "Unknown column 'amonut' in raw_orders",
                    Some("did you mean 'amount'?"),
                    &[
                        "raw_orders has: amount, status, customer_id, order_id",
                        "1 downstream uses of stg.amount were not checked because of this error",
                    ],
                    Some((5, 18, None, None)),
                ),
                described(
                    "B217",
                    "Cannot compare TIMESTAMP and INTEGER",
                    Some("compare with a timestamp, for example TIMESTAMP '2026-04-01'"),
                    &["o.ordered_at is TIMESTAMP, 5 is INTEGER"],
                    Some((7, 7, Some(7), Some(23))),
                ),
                described("B002", "Unknown column 'x' in table 'stg'", None, &[], None),
                described(
                    "P009",
                    "`sql_analysis false` is not needed for model 'legacy'",
                    Some(OPT_OUT_HELP),
                    &[OPT_OUT_NOTE],
                    None,
                ),
            ],
            expected_bindings: Some(vec![vec![0], vec![1], vec![2]]),
        },
        CompletionTestCase {
            description: "non-ASCII authored SQL in an explained model defers to Python",
            non_ascii_comment: true,
            without_diagnostics: false,
            expected_deferral: Some("non_ascii_text"),
            expected_diagnostics: Vec::new(),
            expected_bindings: None,
        },
        CompletionTestCase {
            description: "no diagnostics keep every model's bindings",
            non_ascii_comment: false,
            without_diagnostics: true,
            expected_deferral: None,
            expected_diagnostics: Vec::new(),
            expected_bindings: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            completion_summary(&test_case),
            (
                test_case.expected_deferral,
                test_case.expected_diagnostics.clone(),
                test_case.expected_bindings.clone(),
            ),
            "{}",
            test_case.description
        );
    }
}
