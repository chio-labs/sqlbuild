use crate::dbt_cli::main::build_dbt_argv::build_dbt_argv;
use crate::dbt_cli::main::choose_dbt_config::choose_dbt_config;
use crate::dbt_cli::main::dbt_debug_args::dbt_debug_args;
use crate::dbt_cli::main::resolve_dbt_executable::resolve_dbt_executable;
use crate::dbt_cli::main::route_dbt_interop_args::route_dbt_interop_args;
use crate::dbt_cli::models::{
    DbtArgvCommand, DbtCliOptionValues, DbtConfigChoice, DbtConfigSources, DbtParsedFlags,
};
use crate::dbt_cli::tests::helpers::{buckets, failure, full_options, text, texts};
use crate::dbt_cli::tests::test_types::{ArgvTestCase, ConfigTestCase, RouteTestCase};

#[test]
fn given_debug_flags_when_routing_then_preserves_only_dbt_owned_arguments() {
    let test_cases = [
        ArgvTestCase {
            description: "strip local flags and separate configuration values",
            argv: dbt_debug_args(&texts(&[
                "--project-dir",
                "project",
                "--profiles-dir",
                "profiles",
                "--target",
                "dev",
                "--target-path",
                "target",
                "--no-connection",
                "--connection",
                "--debug",
            ])),
            expected_argv: vec!["--connection", "--debug"],
        },
        ArgvTestCase {
            description: "preserve equals forms for dbt and tolerate a trailing value flag",
            argv: dbt_debug_args(&texts(&["--target=dev", "--no-connection", "--target"])),
            expected_argv: vec!["--target=dev"],
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            test_case.argv, test_case.expected_argv,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_options_when_building_argv_then_orders_flags_like_dbt() {
    let test_cases = [
        ArgvTestCase {
            description: "compile with every option and full refresh",
            argv: build_dbt_argv(
                "dbt",
                &full_options(),
                DbtArgvCommand::Compile { full_refresh: true },
            ),
            expected_argv: vec![
                "dbt",
                "compile",
                "--project-dir",
                "/repo/dbt",
                "--profiles-dir",
                "/repo/profiles",
                "--target",
                "prod",
                "--target-path",
                "/repo/target",
                "--vars",
                "{}",
                "--state",
                "/repo/state",
                "--defer",
                "--full-refresh",
            ],
        },
        ArgvTestCase {
            description: "deps only passes project, profiles, target and vars",
            argv: build_dbt_argv("dbt", &full_options(), DbtArgvCommand::Deps),
            expected_argv: vec![
                "dbt",
                "deps",
                "--project-dir",
                "/repo/dbt",
                "--profiles-dir",
                "/repo/profiles",
                "--target",
                "prod",
                "--vars",
                "{}",
            ],
        },
        ArgvTestCase {
            description: "ls with selectors and resource types",
            argv: build_dbt_argv(
                "bin/dbt",
                &DbtCliOptionValues::default(),
                DbtArgvCommand::Ls {
                    select: texts(&["a", "b+"]),
                    exclude: texts(&["c"]),
                    resource_types: texts(&["model", "seed"]),
                },
            ),
            expected_argv: vec![
                "bin/dbt",
                "ls",
                "--output",
                "json",
                "--select",
                "a",
                "b+",
                "--exclude",
                "c",
                "--resource-type",
                "model",
                "--resource-type",
                "seed",
            ],
        },
        ArgvTestCase {
            description: "another command keeps its arguments last",
            argv: build_dbt_argv(
                "dbt",
                &DbtCliOptionValues {
                    target: text("dev"),
                    ..DbtCliOptionValues::default()
                },
                DbtArgvCommand::Other {
                    command: "build".to_owned(),
                    args: texts(&["--threads", "4"]),
                },
            ),
            expected_argv: vec!["dbt", "build", "--target", "dev", "--threads", "4"],
        },
        ArgvTestCase {
            description: "executable override is stripped and blank falls back",
            argv: vec![
                resolve_dbt_executable(Some("  /opt/dbt \n")),
                resolve_dbt_executable(Some(" \t")),
                resolve_dbt_executable(None),
            ],
            expected_argv: vec!["/opt/dbt", "dbt", "dbt"],
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            test_case.argv, test_case.expected_argv,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_parsed_flags_when_routing_then_splits_buckets_or_rejects() {
    let flags: DbtParsedFlags = DbtParsedFlags {
        select: texts(&["orders+"]),
        vars: text("{a: 1}"),
        threads: text("4"),
        full_refresh: true,
        event_time_start: text("2026-01-01"),
        event_time_end: text("2026-01-02"),
        target: text("prod"),
        defer: true,
        defer_to: text("prod"),
        fail_fast: true,
        dbt_passthrough: texts(&["--warn-error"]),
        ..DbtParsedFlags::default()
    };
    let test_cases = [
        RouteTestCase {
            description: "run routes shared, dbt and SQLBuild flags in order",
            routed: route_dbt_interop_args("run", &flags),
            expected_dbt_args: vec![
                "--select",
                "orders+",
                "--vars",
                "{a: 1}",
                "--threads",
                "4",
                "--full-refresh",
                "--event-time-start",
                "2026-01-01",
                "--event-time-end",
                "2026-01-02",
                "--target",
                "prod",
                "--defer",
                "--warn-error",
            ],
            expected_sqlbuild_args: vec![
                "--vars",
                "{a: 1}",
                "--concurrency",
                "4",
                "--full-refresh",
                "--start-cursor-ts",
                "2026-01-01",
                "--end-cursor-ts",
                "2026-01-02",
                "--defer-to",
                "prod",
                "--fail-fast",
            ],
            expected_error: None,
        },
        RouteTestCase {
            description: "plan rejects --fail-fast",
            routed: route_dbt_interop_args("plan", &flags),
            expected_dbt_args: vec![],
            expected_sqlbuild_args: vec![],
            expected_error: Some((
                "--fail-fast is not a valid SQLBuild option for sqb dbt plan",
                "C232",
            )),
        },
        RouteTestCase {
            description: "unpaired event time",
            routed: route_dbt_interop_args(
                "debug",
                &DbtParsedFlags {
                    event_time_end: text("x"),
                    ..DbtParsedFlags::default()
                },
            ),
            expected_dbt_args: vec![],
            expected_sqlbuild_args: vec![],
            expected_error: Some((
                "--event-time-start and --event-time-end must be provided together",
                "C233",
            )),
        },
        RouteTestCase {
            description: "event time with timestamp cursors",
            routed: route_dbt_interop_args(
                "build",
                &DbtParsedFlags {
                    event_time_start: text("a"),
                    event_time_end: text("b"),
                    end_cursor_ts: text("c"),
                    ..DbtParsedFlags::default()
                },
            ),
            expected_dbt_args: vec![],
            expected_sqlbuild_args: vec![],
            expected_error: Some((
                "--event-time-start/end conflict with --start-cursor-ts/end-cursor-ts",
                "C234",
            )),
        },
        RouteTestCase {
            description: "unknown command",
            routed: route_dbt_interop_args("seed", &DbtParsedFlags::default()),
            expected_dbt_args: vec![],
            expected_sqlbuild_args: vec![],
            expected_error: Some(("Unsupported sqb dbt command: seed", "C236")),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            buckets(&test_case.routed),
            (
                test_case.expected_dbt_args,
                test_case.expected_sqlbuild_args
            ),
            "{}",
            test_case.description
        );
        assert_eq!(
            failure(&test_case.routed),
            test_case.expected_error,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_config_sources_when_choosing_then_prefers_overrides() {
    let sources: DbtConfigSources = DbtConfigSources {
        override_project_dir: text("cli"),
        config_project_dir: text("config"),
        config_profiles_dir: text("profiles"),
        local_target: text("local"),
        config_target: text("config"),
        ..DbtConfigSources::default()
    };
    let test_cases = [
        ConfigTestCase {
            description: "overrides, then local target, then project config",
            choice: choose_dbt_config(sources.clone(), true),
            expected_choice: Ok(DbtConfigChoice {
                project_dir: text("cli"),
                profiles_dir: text("profiles"),
                target_path: None,
                target: text("local"),
            }),
        },
        ConfigTestCase {
            description: "a required project directory must be set",
            choice: choose_dbt_config(DbtConfigSources::default(), true),
            expected_choice: Err("dbt project directory is not configured"),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            test_case.choice.map_err(|error| error.message),
            test_case.expected_choice.map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
