//! Proof callbacks fail transparently and are skipped for ambiguous candidates.

use std::collections::BTreeSet;

use crate::planner_migrations::main::identical_renames::identical_renames;
use crate::planner_migrations::tests::helpers::projection;
use crate::planner_migrations::tests::test_types::ProofTestCase;

#[test]
fn given_candidates_when_proving_then_propagates_failures_and_skips_ambiguity() {
    let test_cases = [
        ProofTestCase {
            description: "lookup error propagates",
            added_names: &["revenue"],
            proof_result: Err("input lookup failed"),
            expected_pairs: Err("input lookup failed"),
            expected_calls: 1,
        },
        ProofTestCase {
            description: "ambiguous pairs skip proof",
            added_names: &["revenue", "total"],
            proof_result: Err("must not call"),
            expected_pairs: Ok(vec![]),
            expected_calls: 0,
        },
        ProofTestCase {
            description: "failed proof rejects pairs",
            added_names: &["revenue"],
            proof_result: Ok(false),
            expected_pairs: Ok(vec![]),
            expected_calls: 1,
        },
        ProofTestCase {
            description: "successful proof keeps pairs",
            added_names: &["revenue"],
            proof_result: Ok(true),
            expected_pairs: Ok(vec![("amount".to_owned(), "revenue".to_owned())]),
            expected_calls: 1,
        },
    ];
    for test_case in test_cases {
        let previous = [projection("amount")];
        let current: Vec<_> = test_case
            .added_names
            .iter()
            .map(|name| projection(name))
            .collect();
        let mut calls = 0;
        let result = identical_renames((&previous, &current), &BTreeSet::new(), &mut |_| {
            calls += 1;
            test_case.proof_result
        });
        assert_eq!(
            result, test_case.expected_pairs,
            "{}",
            test_case.description
        );
        assert_eq!(calls, test_case.expected_calls, "{}", test_case.description);
    }
}
