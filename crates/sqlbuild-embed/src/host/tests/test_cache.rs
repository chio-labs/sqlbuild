#![cfg(target_os = "linux")]

use std::path::PathBuf;

use crate::host::_helpers::cache::cache_file;
use crate::host::main::discover_host::discover_host;
use crate::host::models::HostDiscovery;
use crate::host::tests::helpers::{
    corrupt_cache, edit_venv_config, embeddable, forget, rooted, runs, static_exec, static_venv,
    temporary_root, touch, unchanged, venv, write_executable,
};
use crate::host::tests::test_types::{
    CacheTestCase, MissingInterpreterTestCase, RemovedLibraryTestCase,
};

#[test]
fn given_change_between_discoveries_when_discovering_again_then_cache_is_used_only_if_valid() {
    let test_cases = [
        CacheTestCase {
            description: "an unchanged interpreter is answered from the cache",
            change: unchanged,
            expected_probes: 1,
            expected_found: static_exec,
        },
        CacheTestCase {
            description: "an edited pyvenv.cfg is looked up again",
            change: edit_venv_config,
            expected_probes: 2,
            expected_found: static_exec,
        },
        CacheTestCase {
            description: "a forgotten interpreter is looked up again",
            change: forget,
            expected_probes: 2,
            expected_found: static_exec,
        },
        CacheTestCase {
            description: "a corrupt cache file is replaced",
            change: corrupt_cache,
            expected_probes: 2,
            expected_found: static_exec,
        },
    ];

    for test_case in test_cases {
        let (_directory, root) = temporary_root();
        let venv = static_venv(&root);

        let first = discover_host(&venv.script, Some(&venv.cache));
        (test_case.change)(&venv);
        let second = discover_host(&venv.script, Some(&venv.cache));

        let expected: HostDiscovery = (test_case.expected_found)(&root);
        assert_eq!(first, expected, "{}", test_case.description);
        assert_eq!(second, expected, "{}", test_case.description);
        assert_eq!(
            runs(&venv.runs),
            test_case.expected_probes,
            "{}",
            test_case.description
        );
        assert!(
            cache_file(&venv.cache, &venv.interpreter).is_file(),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_cached_library_removed_when_discovering_then_it_is_looked_up_again() {
    let test_cases = [RemovedLibraryTestCase {
        description: "a removed libpython is noticed through its watched stamp",
        version_line: "version = 3.13.2",
        library: "base/lib/libpython3.13.so.1.0",
        expected_first: |root| {
            embeddable(
                root,
                "venv/bin/python",
                "base/lib/libpython3.13.so.1.0",
                "3.13.2",
            )
        },
        expected_after_removal: |root| {
            HostDiscovery::Exec(rooted(
                "<root>/venv/bin/python described itself unexpectedly",
                root,
            ))
        },
    }];

    for test_case in test_cases {
        let (_directory, root) = temporary_root();
        let interpreter: PathBuf = venv(&root, test_case.version_line);
        touch(&root.join(test_case.library));
        let script: PathBuf = root.join("venv/bin/sqlbuild-python");
        write_executable(&script, &format!("#!{}\n", interpreter.display()));
        let cache: PathBuf = root.join("cache");

        let first = discover_host(&script, Some(&cache));
        let cached = discover_host(&script, Some(&cache));
        std::fs::remove_file(root.join(test_case.library)).expect("remove library");
        let after_removal = discover_host(&script, Some(&cache));

        assert_eq!(
            first,
            (test_case.expected_first)(&root),
            "{}",
            test_case.description
        );
        assert_eq!(cached, first, "{}", test_case.description);
        assert_eq!(
            after_removal,
            (test_case.expected_after_removal)(&root),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_missing_interpreter_when_discovering_then_exec_reports_it() {
    let test_cases = [MissingInterpreterTestCase {
        description: "a #! line naming a removed interpreter",
        head: "#!/nonexistent/bin/python\n",
        expected_found: HostDiscovery::Exec("cannot find /nonexistent/bin/python".to_owned()),
    }];

    for test_case in test_cases {
        let (_directory, root) = temporary_root();
        let script: PathBuf = root.join("sqlbuild-python");
        write_executable(&script, test_case.head);

        let found = discover_host(&script, None);

        assert_eq!(found, test_case.expected_found, "{}", test_case.description);
    }
}
