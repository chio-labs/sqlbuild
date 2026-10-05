use std::collections::HashMap;

use crate::semantic_validation::main::normalize_batch::normalize_analysis_sqls;
use crate::semantic_validation::tests::test_types::NormalizationBatchTestCase;
use crate::semantic_validation::types::NormalizationRequest;

#[test]
fn given_batch_when_normalizing_on_pool_or_in_turn_then_matches_single_calls_in_order() {
    let test_cases = [
        NormalizationBatchTestCase {
            description: "stubbed references and placeholders",
            dialect: "snowflake",
            requests: &[
                (
                    r#"SELECT * FROM __ref("orders") JOIN __ref("customers") USING (id)"#,
                    &[("orders", "__sqb_rel_0"), ("customers", "__sqb_rel_1")],
                ),
                ("SELECT payload:item[0] AS item FROM inventory", &[]),
                ("SELECT 1 LIMIT @@@limit", &[]),
            ],
            expected_failures: &[],
        },
        NormalizationBatchTestCase {
            description: "failures stay at their own positions",
            dialect: "snowflake",
            requests: &[
                ("SELECT 'unterminated FROM orders", &[]),
                ("SELECT id FROM products", &[]),
                ("SELECT /* unterminated FROM customers", &[]),
            ],
            expected_failures: &[0, 2],
        },
    ];
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(3)
        .build()
        .expect("test pool must build");

    for test_case in test_cases {
        let requests = || -> Vec<NormalizationRequest> {
            test_case
                .requests
                .iter()
                .map(|(sql, stubs)| {
                    (
                        (*sql).to_owned(),
                        stubs
                            .iter()
                            .map(|(name, stub)| ((*name).to_owned(), (*stub).to_owned()))
                            .collect(),
                        HashMap::from([("limit".to_owned(), "10".to_owned())]),
                    )
                })
                .collect()
        };
        let expected: Vec<Result<String, String>> = requests()
            .into_iter()
            .map(|(sql, stubs, placeholders)| {
                crate::semantic_validation::_helpers::normalization::normalize_analysis_sql(
                    &sql,
                    test_case.dialect,
                    stubs,
                    placeholders,
                )
            })
            .collect();
        let failures: Vec<usize> = (0..expected.len())
            .filter(|index| expected[*index].is_err())
            .collect();

        assert_eq!(
            failures, test_case.expected_failures,
            "{}",
            test_case.description
        );
        assert_eq!(
            normalize_analysis_sqls(test_case.dialect, requests(), Some(&pool)),
            expected,
            "{}",
            test_case.description
        );
        assert_eq!(
            normalize_analysis_sqls(test_case.dialect, requests(), None),
            expected,
            "{}",
            test_case.description
        );
    }
}
