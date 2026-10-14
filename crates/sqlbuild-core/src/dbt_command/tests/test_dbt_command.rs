use crate::cli_text::models::CliStyle;
use crate::dbt_command::main::dbt_output_options::dbt_output_options;
use crate::dbt_command::main::dbt_value_arg::dbt_value_arg;
use crate::dbt_command::main::forwarded_dbt_args::forwarded_dbt_args;
use crate::dbt_command::main::render_dbt_auto_init::render_dbt_auto_init;
use crate::dbt_command::main::render_dbt_init_preview::render_dbt_init_preview;
use crate::dbt_command::main::render_dbt_init_summary::render_dbt_init_summary;
use crate::dbt_command::models::{DbtOutputOptions, ForwardedArg};
use crate::dbt_command::tests::helpers::{summary, texts};
use crate::dbt_command::tests::test_types::{ArgsTestCase, RenderTestCase};

const PLAIN: CliStyle = CliStyle { use_color: false };

#[test]
fn given_forwarded_args_when_reading_them_then_splits_output_flags_and_paths() {
    let test_cases = [
        ArgsTestCase {
            description: "output flags are removed and path values marked",
            args: texts(&[
                "--json",
                "--select",
                "a",
                "-v",
                "--profiles-dir",
                "p",
                "--target",
                "prod",
            ]),
            expected_options: DbtOutputOptions {
                json_output: true,
                verbose: true,
                routed_args: texts(&["--select", "a", "--profiles-dir", "p", "--target", "prod"]),
            },
            expected_forwarded: vec![
                ForwardedArg::Literal("--json".to_owned()),
                ForwardedArg::Literal("--select".to_owned()),
                ForwardedArg::Literal("a".to_owned()),
                ForwardedArg::Literal("-v".to_owned()),
                ForwardedArg::Literal("--profiles-dir".to_owned()),
                ForwardedArg::Path("p".to_owned()),
                ForwardedArg::Literal("--target".to_owned()),
                ForwardedArg::Literal("prod".to_owned()),
            ],
            expected_target: Some("prod".to_owned()),
        },
        ArgsTestCase {
            description: "a trailing path flag and a valueless target",
            args: texts(&["--target", "--project-dir"]),
            expected_options: DbtOutputOptions {
                json_output: false,
                verbose: false,
                routed_args: texts(&["--target", "--project-dir"]),
            },
            expected_forwarded: vec![
                ForwardedArg::Literal("--target".to_owned()),
                ForwardedArg::Literal("--project-dir".to_owned()),
            ],
            expected_target: Some("--project-dir".to_owned()),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            dbt_output_options(&test_case.args),
            test_case.expected_options,
            "{}",
            test_case.description
        );
        assert_eq!(
            forwarded_dbt_args(&test_case.args),
            test_case.expected_forwarded,
            "{}",
            test_case.description
        );
        assert_eq!(
            dbt_value_arg(&test_case.args, "--target"),
            test_case.expected_target,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_setup_result_when_rendering_then_writes_the_setup_documents() {
    let test_cases = [
        RenderTestCase {
            description: "auto-init notice",
            rendered: render_dbt_auto_init("/w/sqlbuild_project.toml", PLAIN),
            expected_text: "\nSQLBuild dbt setup created\n\nSetup summary:\n  Config file               /w/sqlbuild_project.toml\n\nWhat SQLBuild created: a twin config that points SQLBuild at your dbt project and profile.\n",
        },
        RenderTestCase {
            description: "dry-run preview",
            rendered: render_dbt_init_preview(&summary(), PLAIN),
            expected_text: "\nSQLBuild project preview\n\n  Project: analytics\n  Config file:  /w/sqlbuild_project/sqlbuild_project.toml\n  Adapter: duckdb\n  Target:  dev\n  Profile: analytics\n\nGenerated config:\nname = \"analytics\"\n",
        },
        RenderTestCase {
            description: "created summary",
            rendered: render_dbt_init_summary(&summary(), PLAIN),
            expected_text: "\nSQLBuild project created\n\nSetup summary:\n  Project                   analytics\n  Config file               /w/sqlbuild_project/sqlbuild_project.toml\n  Adapter                   duckdb\n  Target                    dev\n  Profile                   analytics\n\nWhat SQLBuild created:\n  1. SQLBuild twin config (sqlbuild_project.toml)\n     This points SQLBuild at your dbt project and profile. Edit it if dbt paths\n     or profile targets need to change.\n\nNext steps:\n  1. cd /w/sqlbuild_project\n  2. Review the config file above.\n  3. sqb dbt debug\n  4. sqb dbt build\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            test_case.rendered, test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
