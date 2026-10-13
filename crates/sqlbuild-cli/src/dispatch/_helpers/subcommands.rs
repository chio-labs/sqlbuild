//! Subcommand routes and the user errors the dispatcher raises before a handler runs.

use crate::dispatch::constants::{
    DBT_BUILD_ROUTE, DBT_DEBUG_ROUTE, DBT_INIT_ROUTE, DBT_PLAN_ROUTE, DBT_RUN_ROUTE,
    SCENARIO_CAPTURE_ROUTE, SCENARIO_TEST_ROUTE,
};
use crate::dispatch::models::{CommandFacts, Dispatch, DispatchFailure, Route};

pub(crate) fn failure(
    message: &str,
    code: &'static str,
    help: Option<&'static str>,
) -> DispatchFailure {
    DispatchFailure {
        message: message.to_owned(),
        code,
        help,
    }
}

pub(crate) fn dbt_dispatch(subcommand: &str) -> Dispatch {
    let route: &'static Route = match subcommand {
        "init" => &DBT_INIT_ROUTE,
        "plan" => &DBT_PLAN_ROUTE,
        "run" => &DBT_RUN_ROUTE,
        "build" => &DBT_BUILD_ROUTE,
        "debug" => &DBT_DEBUG_ROUTE,
        _ => {
            return Dispatch::Fail(failure(
                "dbt requires a subcommand such as 'plan'",
                "C237",
                None,
            ));
        }
    };
    Dispatch::Run(route, None)
}

pub(crate) fn scenario_dispatch(facts: &CommandFacts, subcommand: &str) -> Dispatch {
    match subcommand {
        "test" if facts.scenario_local && facts.scenario_retain => Dispatch::Fail(failure(
            "scenario test --local does not support --retain",
            "C452",
            Some("Local scenario DuckDB files are always kept under target/run/scenarios/."),
        )),
        "test" if !facts.scenario_local && facts.scenario_snapshot_sync => Dispatch::Fail(failure(
            "scenario snapshot sync flags require --local",
            "C454",
            Some(
                "Use sqb scenario test --local --sync-snapshots or sqb scenario test --local \
                     --refresh.",
            ),
        )),
        "test" => Dispatch::Run(&SCENARIO_TEST_ROUTE, None),
        "capture" => Dispatch::Run(&SCENARIO_CAPTURE_ROUTE, None),
        _ => Dispatch::Fail(failure(
            "scenario requires a subcommand such as 'test'",
            "C450",
            None,
        )),
    }
}

pub(crate) fn format_failure(facts: &CommandFacts) -> Option<DispatchFailure> {
    if facts.format_diff && facts.json {
        return Some(failure(
            "format --diff cannot be combined with --json",
            "C112",
            None,
        ));
    }
    (facts.format_fix && facts.format_fixtures_only).then(|| {
        failure(
            "format --fix cannot be combined with --fixtures-only",
            "C112",
            None,
        )
    })
}
