use crate::semantic_checks::tests::helpers::{
    expected_bindings, expected_kept, expected_poisoned, recovery_summary,
};
use crate::semantic_checks::tests::test_types::TypeRecoveryTestCase;

const DOWNSTREAM_NOTE: &str =
    "2 downstream output uses were not type-checked because of this error";
const POISONED: &[(&str, &str)] = &[("stg", "amount"), ("mart", "total"), ("report", "x")];

#[test]
fn given_poisoned_projection_when_recovering_types_then_counts_and_drops_like_python() {
    let test_cases = [
        TypeRecoveryTestCase {
            description: "a downstream error the unknown type explains is dropped",
            dialect: Some("duckdb"),
            errors: true,
            revised: &[],
            expected_status: "planned",
            expected_poisoned: POISONED,
            expected_revalidated: &[1],
            expected_kept: &[(0, Some(DOWNSTREAM_NOTE))],
            expected_bindings: &[&[0], &[], &[]],
        },
        TypeRecoveryTestCase {
            description: "a downstream error the revalidation still reports is kept",
            dialect: Some("duckdb"),
            errors: true,
            revised: &[("B217", Some(56), Some(62))],
            expected_status: "planned",
            expected_poisoned: POISONED,
            expected_revalidated: &[1],
            expected_kept: &[(0, Some(DOWNSTREAM_NOTE)), (1, None)],
            expected_bindings: &[&[0], &[1], &[]],
        },
        TypeRecoveryTestCase {
            description: "no dialect, which the wheel's tokenizer rejects",
            dialect: None,
            errors: true,
            revised: &[],
            expected_status: "unsupported_dialect",
            expected_poisoned: &[],
            expected_revalidated: &[],
            expected_kept: &[],
            expected_bindings: &[],
        },
        TypeRecoveryTestCase {
            description: "only warnings leave the project unchanged",
            dialect: Some("duckdb"),
            errors: false,
            revised: &[],
            expected_status: "unchanged",
            expected_poisoned: &[],
            expected_revalidated: &[],
            expected_kept: &[],
            expected_bindings: &[],
        },
    ];
    for test_case in test_cases {
        let (status, poisoned, revalidated, kept, bindings) = recovery_summary(&test_case);
        assert_eq!(
            status, test_case.expected_status,
            "{}",
            test_case.description
        );
        assert_eq!(
            poisoned,
            expected_poisoned(test_case.expected_poisoned),
            "{}",
            test_case.description
        );
        assert_eq!(
            revalidated, test_case.expected_revalidated,
            "{}",
            test_case.description
        );
        assert_eq!(
            kept,
            expected_kept(test_case.expected_kept),
            "{}",
            test_case.description
        );
        assert_eq!(
            bindings,
            expected_bindings(test_case.expected_bindings),
            "{}",
            test_case.description
        );
    }
}
