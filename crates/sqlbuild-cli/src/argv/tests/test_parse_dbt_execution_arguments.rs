use sqlbuild_core::dbt_cli::models::DbtParsedFlags;

use crate::argv::main::parse_dbt_execution_arguments::parse_dbt_execution_arguments;
use crate::argv::models::{ArgvSettings, DbtExecutionFailure};
use crate::argv::tests::helpers::owned;
use crate::argv::tests::test_types::DbtExecutionTestCase;

#[test]
fn given_dbt_execution_arguments_when_parsing_then_flags_or_failures_match_argparse() {
    let test_cases = [
        DbtExecutionTestCase {
            description: "declared flags, stray positionals and the -- tail",
            args: &[
                "-s",
                "a",
                "b",
                "--full-refresh",
                "extra",
                "--",
                "--log-level",
                "debug",
            ],
            expected_parsed: Ok(DbtParsedFlags {
                select: owned(&["a", "b"]),
                full_refresh: true,
                dbt_passthrough: owned(&["extra", "--log-level", "debug"]),
                ..DbtParsedFlags::default()
            }),
        },
        DbtExecutionTestCase {
            description: "an ambiguous abbreviation lists its matches",
            args: &["--targ=prod"],
            expected_parsed: Err(DbtExecutionFailure::Argument(
                "sqb dbt run: ambiguous option: --targ=prod could match --target, --target-path"
                    .to_owned(),
            )),
        },
        DbtExecutionTestCase {
            description: "unique abbreviations extend the selection",
            args: &["x", "--sel", "a", "--se", "y"],
            expected_parsed: Ok(DbtParsedFlags {
                select: owned(&["a", "y"]),
                dbt_passthrough: owned(&["x"]),
                ..DbtParsedFlags::default()
            }),
        },
        DbtExecutionTestCase {
            description: "an unknown option is unrecognized",
            args: &["--bogus", "--", "--bogus-too"],
            expected_parsed: Err(DbtExecutionFailure::Unrecognized(owned(&["--bogus"]))),
        },
        DbtExecutionTestCase {
            description: "a missing value is an argument error under the command's prog",
            args: &["--select"],
            expected_parsed: Err(DbtExecutionFailure::Argument(
                "sqb dbt run: argument --select/-s: expected at least one argument".to_owned(),
            )),
        },
        DbtExecutionTestCase {
            description: "help exits successfully",
            args: &["-h"],
            expected_parsed: Err(DbtExecutionFailure::Exit(0)),
        },
    ];

    for test_case in test_cases {
        let settings: ArgvSettings = ArgvSettings {
            columns: 100,
            use_color: false,
        };
        let outcome = parse_dbt_execution_arguments("run", &owned(test_case.args), settings);
        assert_eq!(
            outcome.parsed, test_case.expected_parsed,
            "{}",
            test_case.description
        );
    }
}
