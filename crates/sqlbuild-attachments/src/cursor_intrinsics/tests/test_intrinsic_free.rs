use crate::cursor_intrinsics::main::intrinsic_free::intrinsic_free;
use crate::cursor_intrinsics::models::IntrinsicCheck;
use crate::cursor_intrinsics::tests::test_types::IntrinsicCheckTestCase;

#[test]
fn given_sql_when_checking_cursor_intrinsics_then_python_acceptance_is_returned() {
    let test_cases = [
        IntrinsicCheckTestCase {
            description: "SQL without intrinsic names is free",
            sql: "SELECT 'unclosed",
            expected_check: IntrinsicCheck::Free,
        },
        IntrinsicCheckTestCase {
            description: "names inside quotes, comments, dollar quotes and identifiers are free",
            sql: "SELECT '__cursor_start()', `a``__cursor_end`, x__cursor_end -- __cursor_end\n\
                  /* __cursor_start */ $tag$__cursor_end()$tag$, __cursor_start_at",
            expected_check: IntrinsicCheck::Free,
        },
        IntrinsicCheckTestCase {
            description: "an intrinsic call defers so Python raises",
            sql: "WHERE ts >= __cursor_start()",
            expected_check: IntrinsicCheck::Deferred,
        },
        IntrinsicCheckTestCase {
            description: "an unclosed quote after an intrinsic name defers",
            sql: "SELECT x__cursor_start, 'open",
            expected_check: IntrinsicCheck::Deferred,
        },
        IntrinsicCheckTestCase {
            description: "a non-ASCII neighbour defers to Python's Unicode identifier rules",
            sql: "SELECT é__cursor_end",
            expected_check: IntrinsicCheck::Deferred,
        },
        IntrinsicCheckTestCase {
            description: "a reserved marker defers",
            sql: "SELECT __reserved_marker__",
            expected_check: IntrinsicCheck::Deferred,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            intrinsic_free(test_case.sql, &["__reserved_marker__".to_owned()]),
            test_case.expected_check,
            "{}",
            test_case.description
        );
    }
}
