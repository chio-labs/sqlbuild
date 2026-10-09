use crate::semantic_checks::tests::helpers::{described, operand_type_summary};
use crate::semantic_checks::tests::test_types::OperandTypeTestCase;

const ARITHMETIC_MESSAGE: &str =
    "Arithmetic operation expects NUMERIC-compatible operands, found TIMESTAMP and INTEGER";
const ARITHMETIC_HELP: &str =
    "use operands supported by this arithmetic operator, or convert them explicitly";
const COMPARISON_MESSAGE: &str = "Incompatible comparison between TIMESTAMP and INTEGER";
const TIMESTAMP_HELP: &str = "compare with a timestamp, for example TIMESTAMP '2026-04-01'";

#[test]
fn given_unqualified_operand_types_when_explaining_then_notes_only_known_types_like_python() {
    let test_cases = [
        OperandTypeTestCase {
            description: "an empty column type is no type, so neither error gets a note",
            joined: "",
            shapes: &[("stg", &[("order_id", "INTEGER"), ("ordered_at", "")])],
            expected_diagnostics: vec![
                described(
                    "B212",
                    ARITHMETIC_MESSAGE,
                    Some(ARITHMETIC_HELP),
                    &[],
                    Some((5, 18, Some(5), Some(32))),
                ),
                described(
                    "B217",
                    COMPARISON_MESSAGE,
                    Some(TIMESTAMP_HELP),
                    &[],
                    Some((7, 7, Some(7), Some(21))),
                ),
            ],
        },
        OperandTypeTestCase {
            description: "an empty and an INTEGER type across two inputs stay ambiguous",
            joined: " JOIN __ref(\"orders\") ON TRUE",
            shapes: &[
                ("stg", &[("order_id", "INTEGER"), ("ordered_at", "")]),
                ("orders", &[("ordered_at", "INTEGER")]),
            ],
            expected_diagnostics: vec![
                described(
                    "B212",
                    ARITHMETIC_MESSAGE,
                    Some(ARITHMETIC_HELP),
                    &[],
                    Some((5, 18, Some(5), Some(32))),
                ),
                described(
                    "B217",
                    COMPARISON_MESSAGE,
                    Some(TIMESTAMP_HELP),
                    &[],
                    Some((7, 7, Some(7), Some(21))),
                ),
            ],
        },
        OperandTypeTestCase {
            description: "a known type is noted for both errors",
            joined: "",
            shapes: &[(
                "stg",
                &[("order_id", "INTEGER"), ("ordered_at", "timestamp")],
            )],
            expected_diagnostics: vec![
                described(
                    "B212",
                    ARITHMETIC_MESSAGE,
                    Some(ARITHMETIC_HELP),
                    &["ordered_at is TIMESTAMP, 1 is INTEGER"],
                    Some((5, 18, Some(5), Some(32))),
                ),
                described(
                    "B217",
                    COMPARISON_MESSAGE,
                    Some(TIMESTAMP_HELP),
                    &["ordered_at is TIMESTAMP, 5 is INTEGER"],
                    Some((7, 7, Some(7), Some(21))),
                ),
            ],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            operand_type_summary(&test_case),
            (
                None,
                test_case.expected_diagnostics.clone(),
                Some(vec![vec![0, 1]])
            ),
            "{}",
            test_case.description
        );
    }
}
