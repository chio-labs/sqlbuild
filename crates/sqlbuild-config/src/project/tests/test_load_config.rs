use crate::project::models::ConfigFile;
use crate::project::tests::helpers::{failure_at, first_failure, project_directory};
use crate::project::tests::test_types::ProjectFailureTestCase;

const PROJECT: &str = "name = 'orders'\nadapter = 'duckdb'\n";

#[test]
fn given_project_files_when_loading_then_rejections_match_python_loader() {
    let test_cases = [
        ProjectFailureTestCase {
            description: "a valid project and local file load",
            project: "name = 'orders'\nadapter = 'duckdb'\n[settings]\nconcurrency = 4\n\
                      [targets.dev]\nschema = 'analytics'\n[sinks.lifecycle]\nshutdown_timeout = '10m'\n",
            local: "target = 'dev'\n[settings]\nmax_concurrency = 2\n",
            expected_failure: None,
        },
        ProjectFailureTestCase {
            description: "an unknown key suggests the nearest supported key",
            project: "name = 'orders'\nadapter = 'duckdb'\n[scopes]\nenforce_placment = true\n",
            local: "",
            expected_failure: failure_at(
                ConfigFile::Project,
                "scopes contains unknown key(s): enforce_placment. Allowed keys: enforce_placement",
                Some("did you mean 'enforce_placement'?"),
            ),
        },
        ProjectFailureTestCase {
            description: "the janitor requires query change tracking to delete tracked relations",
            project: "name = 'orders'\nadapter = 'duckdb'\n[settings]\nquery_change_tracking = false\n\
                      [janitor]\nenabled = true\n",
            local: "",
            expected_failure: failure_at(
                ConfigFile::Project,
                "[janitor] delete_tracked_only = true requires query change tracking; \
                 sqlbuild_project.toml sets [settings] query_change_tracking = false",
                Some(
                    "to track which relations SQLBuild created, set this in sqlbuild_project.toml:\n\
                     \x20           [settings]\n            query_change_tracking = true",
                ),
            ),
        },
        ProjectFailureTestCase {
            description: "a shutdown timeout over ten minutes is rejected",
            project: "name = 'orders'\nadapter = 'duckdb'\n[sinks.lifecycle]\nshutdown_timeout = '601s'\n",
            local: "",
            expected_failure: failure_at(
                ConfigFile::Project,
                "sinks.lifecycle.shutdown_timeout must be a fixed duration from '0s' to '10m' such as '30s'",
                None,
            ),
        },
        ProjectFailureTestCase {
            description: "a local file cannot set the shared SQL analysis policy",
            project: PROJECT,
            local: "[settings]\nrequire_sql_analysis = true\n",
            expected_failure: failure_at(
                ConfigFile::Local,
                "cannot set [settings] require_sql_analysis; it is a shared project policy that \
                 only sqlbuild_project.toml can set",
                Some(
                    "remove require_sql_analysis from sqlbuild_local.toml\n  = help: to change the \
                     policy for everyone, set this in sqlbuild_project.toml:\n            [settings]\n\
                     \x20           require_sql_analysis = false",
                ),
            ),
        },
        ProjectFailureTestCase {
            description: "a path default normalizing to an existing key is rejected",
            project: "name = 'orders'\nadapter = 'duckdb'\n[path_defaults.staging]\n[path_defaults.' staging ']\n",
            local: "",
            expected_failure: failure_at(
                ConfigFile::Project,
                "path_defaults defines both ' staging ' and another key that normalize to \
                 'staging'. Use only the canonical model-relative form without a leading \
                 'models/' prefix.",
                None,
            ),
        },
    ];

    for test_case in test_cases {
        let (_directory, paths) = project_directory(test_case.project, test_case.local);

        let failure = first_failure(&paths);

        assert_eq!(
            failure, test_case.expected_failure,
            "{}",
            test_case.description
        );
    }
}
