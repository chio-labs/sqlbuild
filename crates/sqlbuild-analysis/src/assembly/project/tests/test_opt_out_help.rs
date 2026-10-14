use crate::assembly::project::main::sql_analysis_opt_out_help::sql_analysis_opt_out_help;
use crate::assembly::project::tests::test_types::OptOutHelpTestCase;

#[test]
fn given_ownership_when_rendering_opt_out_help_then_matches_python_help() {
    let test_cases = [
        OptOutHelpTestCase {
            description: "model-owned SQL offers the MODEL header entry",
            model_owned: true,
            expected_help: "if this SQL is valid for your warehouse, skip SQL analysis for this \
                model, add this to the MODEL header:\n            MODEL (\n              \
                sql_analysis false,\n              ...\n            );\n          and please \
                report the SQL so the parser can support it\n  = help: SQL analysis is on for \
                this project; to turn it off for every model, set this in \
                sqlbuild_project.toml:\n            [settings]\n            sql_analysis = \
                false\n  = help: to skip SQL analysis for one run, use `--no-sql-analysis`",
        },
        OptOutHelpTestCase {
            description: "other SQL only asks for a report",
            model_owned: false,
            expected_help: "if this SQL is valid for your warehouse, please report it so the \
                parser can support it\n  = help: SQL analysis is on for this project; to turn \
                it off for every model, set this in sqlbuild_project.toml:\n            \
                [settings]\n            sql_analysis = false\n  = help: to skip SQL analysis \
                for one run, use `--no-sql-analysis`",
        },
    ];

    for test_case in test_cases {
        let help: String = sql_analysis_opt_out_help(test_case.model_owned);

        assert_eq!(help, test_case.expected_help, "{}", test_case.description);
    }
}
