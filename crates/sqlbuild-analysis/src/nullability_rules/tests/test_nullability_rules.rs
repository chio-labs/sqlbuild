use crate::nullability_rules::main::conditional_result_nullability::conditional_result_nullability;
use crate::nullability_rules::main::first_arg_nullability::first_arg_nullability;
use crate::nullability_rules::main::safe_cast_nullability::safe_cast_nullability;
use crate::nullability_rules::tests::test_types::NullabilityRuleTestCase;

#[test]
fn given_argument_nullabilities_when_inferred_then_each_rule_matches_its_contract() {
    let test_cases = [
        NullabilityRuleTestCase {
            description: "no arguments",
            arguments: vec![],
            expected_first_arg: "unknown",
            expected_conditional: "unknown",
            expected_safe_cast: "unknown",
        },
        NullabilityRuleTestCase {
            description: "a nullable value only",
            arguments: vec!["nullable"],
            expected_first_arg: "nullable",
            expected_conditional: "unknown",
            expected_safe_cast: "nullable",
        },
        NullabilityRuleTestCase {
            description: "two non-null results",
            arguments: vec!["unknown", "non_null", "non_null"],
            expected_first_arg: "unknown",
            expected_conditional: "non_null",
            expected_safe_cast: "unknown",
        },
        NullabilityRuleTestCase {
            description: "one nullable result",
            arguments: vec!["non_null", "non_null", "nullable", "nullable"],
            expected_first_arg: "non_null",
            expected_conditional: "nullable",
            expected_safe_cast: "unknown",
        },
        NullabilityRuleTestCase {
            description: "an unproven result",
            arguments: vec!["nullable", "non_null", "unknown"],
            expected_first_arg: "nullable",
            expected_conditional: "unknown",
            expected_safe_cast: "nullable",
        },
        NullabilityRuleTestCase {
            description: "an unrecognised value",
            arguments: vec!["other", "other", "non_null"],
            expected_first_arg: "other",
            expected_conditional: "unknown",
            expected_safe_cast: "unknown",
        },
    ];
    for test_case in test_cases {
        let actual = (
            first_arg_nullability(&test_case.arguments),
            conditional_result_nullability(&test_case.arguments),
            safe_cast_nullability(&test_case.arguments),
        );
        assert_eq!(
            actual,
            (
                test_case.expected_first_arg,
                test_case.expected_conditional,
                test_case.expected_safe_cast
            ),
            "{}",
            test_case.description
        );
    }
}
