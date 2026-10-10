use crate::cursor_intrinsics::main::intrinsic_free::intrinsic_free;
use crate::cursor_intrinsics::models::IntrinsicCheck;
use crate::cursor_intrinsics::tests::helpers::{python, rejected};
use crate::cursor_intrinsics::tests::test_types::IntrinsicCheckTestCase;

#[test]
fn given_sql_when_checking_cursor_intrinsics_then_python_acceptance_or_error_is_returned() {
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
            description: "a well-formed call is rejected once the whole SQL is scanned",
            sql: "WHERE ts >= __cursor_start( ) AND ts < __cursor_end\t()",
            expected_check: rejected(
                "Audit 'fresh' uses cursor intrinsics, which are only supported in cursor-based \
                 incremental model query SQL",
            ),
        },
        IntrinsicCheckTestCase {
            description: "a later malformed call is raised before the use itself",
            sql: "WHERE ts >= __cursor_start() AND ts < __cursor_end",
            expected_check: rejected("Audit 'fresh' intrinsic __cursor_end must be called with ()"),
        },
        IntrinsicCheckTestCase {
            description: "call arguments are rejected",
            sql: "WHERE ts >= __cursor_end(1 - 2)",
            expected_check: rejected(
                "Audit 'fresh' intrinsic __cursor_end does not accept arguments",
            ),
        },
        IntrinsicCheckTestCase {
            description: "an unclosed call names the cursor intrinsic context",
            sql: "WHERE ts >= __cursor_start(",
            expected_check: rejected(
                "Audit 'fresh' cursor intrinsic contains an unclosed parenthesis",
            ),
        },
        IntrinsicCheckTestCase {
            description: "an unclosed quote after an intrinsic name is Python's quote error",
            sql: "SELECT x__cursor_start, 'open",
            expected_check: rejected("Audit 'fresh' contains an unclosed quoted string"),
        },
        IntrinsicCheckTestCase {
            description: "an unclosed block comment before a call is Python's comment error",
            sql: "SELECT __cursor_end() /* open",
            expected_check: rejected("Audit 'fresh' contains an unclosed block comment"),
        },
        IntrinsicCheckTestCase {
            description: "a reserved marker is rejected first",
            sql: "SELECT __reserved_marker__, __cursor_start(",
            expected_check: rejected("Audit 'fresh' contains a reserved internal cursor marker"),
        },
        IntrinsicCheckTestCase {
            description: "a quoted parenthesis inside a call is an argument",
            sql: "WHERE ts >= __cursor_start(')')",
            expected_check: rejected(
                "Audit 'fresh' intrinsic __cursor_start does not accept arguments",
            ),
        },
        IntrinsicCheckTestCase {
            description: "a comment-only call is an argument",
            sql: "WHERE ts >= __cursor_start(/* now */)",
            expected_check: rejected(
                "Audit 'fresh' intrinsic __cursor_start does not accept arguments",
            ),
        },
        IntrinsicCheckTestCase {
            description: "an unclosed quote inside a call names the cursor intrinsic context",
            sql: "WHERE ts >= __cursor_start('open",
            expected_check: rejected(
                "Audit 'fresh' cursor intrinsic contains an unclosed quoted string",
            ),
        },
        IntrinsicCheckTestCase {
            description: "a non-ASCII letter neighbour continues the identifier",
            sql: "SELECT é__cursor_end, __cursor_endé",
            expected_check: IntrinsicCheck::Free,
        },
        IntrinsicCheckTestCase {
            description: "a non-ASCII symbol neighbour is a boundary",
            sql: "SELECT ·__cursor_end",
            expected_check: rejected("Audit 'fresh' intrinsic __cursor_end must be called with ()"),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            intrinsic_free(
                python(),
                test_case.sql,
                &["__reserved_marker__".to_owned()],
                "Audit 'fresh'"
            ),
            test_case.expected_check,
            "{}",
            test_case.description
        );
    }
}
