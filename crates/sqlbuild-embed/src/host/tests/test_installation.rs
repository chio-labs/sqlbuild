use std::path::{Path, PathBuf};

use crate::host::_helpers::installation::{
    installed_library, locate_library, parse_venv_config, release_version,
};
use crate::host::models::HostDiscovery;
use crate::host::tests::helpers::{
    describing_interpreter, embeddable, linked_base_interpreter, located, rooted, temporary_root,
    touch, venv, venv_with_shared_base,
};
use crate::host::tests::test_types::{
    LibraryLayoutTestCase, LocateTestCase, ProbeTestCase, ReleaseVersionTestCase,
    VenvConfigTestCase,
};

#[test]
fn given_venv_configs_when_parsing_then_home_and_release_are_read() {
    let test_cases = [
        VenvConfigTestCase {
            description: "the venv module's version key",
            text: "home = /opt/python/bin\nversion = 3.12.3\n",
            expected_home: Some("/opt/python/bin"),
            expected_version: Some("3.12.3"),
        },
        VenvConfigTestCase {
            description: "virtualenv's version_info key without spaces around the home",
            text: "home=/opt/python/bin\nversion_info = 3.13.1.final.0\n",
            expected_home: Some("/opt/python/bin"),
            expected_version: Some("3.13.1"),
        },
        VenvConfigTestCase {
            description: "uv's minor version and a capitalised key",
            text: "Home = /opt/python/bin\nuv = 0.12.3\nversion_info = 3.14\n",
            expected_home: Some("/opt/python/bin"),
            expected_version: Some("3.14"),
        },
        VenvConfigTestCase {
            description: "a configuration naming neither",
            text: "include-system-site-packages = false\n",
            expected_home: None,
            expected_version: None,
        },
    ];

    for test_case in test_cases {
        let parsed = parse_venv_config(test_case.text);

        assert_eq!(
            parsed,
            (
                test_case.expected_home.map(PathBuf::from),
                test_case.expected_version.map(str::to_owned)
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_version_texts_when_reading_release_then_only_numbered_releases_count() {
    let test_cases = [
        ReleaseVersionTestCase {
            description: "a full release",
            text: "3.12.13",
            expected_release: Some("3.12.13"),
        },
        ReleaseVersionTestCase {
            description: "a pre-release keeps its numbered parts",
            text: "3.14.0rc1",
            expected_release: Some("3.14"),
        },
        ReleaseVersionTestCase {
            description: "a major version alone",
            text: "3",
            expected_release: None,
        },
        ReleaseVersionTestCase {
            description: "a debug interpreter name",
            text: "3.12d",
            expected_release: None,
        },
    ];

    for test_case in test_cases {
        let release: Option<String> = release_version(test_case.text);

        assert_eq!(
            release.as_deref(),
            test_case.expected_release,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_library_layouts_when_locating_then_first_shared_libpython_of_the_version_wins() {
    let test_cases = [
        LibraryLayoutTestCase {
            description: "the versioned soname in lib",
            files: &["lib/libpython3.12.so.1.0", "lib/libpython3.12.so"],
            expected_library: Some("<root>/lib/libpython3.12.so.1.0"),
        },
        LibraryLayoutTestCase {
            description: "the development link when no soname file exists",
            files: &["lib/libpython3.12.so"],
            expected_library: Some("<root>/lib/libpython3.12.so"),
        },
        LibraryLayoutTestCase {
            description: "lib64",
            files: &["lib64/libpython3.12.so.1.0"],
            expected_library: Some("<root>/lib64/libpython3.12.so.1.0"),
        },
        LibraryLayoutTestCase {
            description: "the Debian multiarch directory",
            files: &["lib/<arch>-linux-gnu/libpython3.12.so.1.0"],
            expected_library: Some("<root>/lib/<arch>-linux-gnu/libpython3.12.so.1.0"),
        },
        LibraryLayoutTestCase {
            description: "another minor version and the stable ABI library are never used",
            files: &["lib/libpython3.13.so.1.0", "lib/libpython3.so"],
            expected_library: None,
        },
        LibraryLayoutTestCase {
            description: "a static library is not loadable",
            files: &["lib/libpython3.12.a"],
            expected_library: None,
        },
    ];

    for test_case in test_cases {
        let (_directory, root) = temporary_root();
        for file in test_case.files {
            touch(&root.join(rooted(file, Path::new(""))));
        }

        let library: Option<PathBuf> = installed_library(&root, 12);

        assert_eq!(
            library,
            test_case
                .expected_library
                .map(|expected| PathBuf::from(rooted(expected, &root))),
            "{}",
            test_case.description
        );
    }
}

#[cfg(unix)]
#[test]
fn given_installations_when_locating_then_their_own_libpython_is_embeddable() {
    let test_cases = [
        LocateTestCase {
            description: "a venv whose base has a shared libpython, at the venv's release",
            prepare: venv_with_shared_base,
            expected_located: |root| {
                located(
                    embeddable(
                        root,
                        "venv/bin/python",
                        "base/lib/libpython3.12.so.1.0",
                        "3.12.13",
                    ),
                    true,
                    Some(root.join("base/lib/libpython3.12.so.1.0")),
                )
            },
        },
        LocateTestCase {
            description: "a base interpreter link takes its version from the linked name",
            prepare: linked_base_interpreter,
            expected_located: |root| {
                located(
                    embeddable(
                        root,
                        "prefix/bin/python3",
                        "prefix/lib/libpython3.13.so.1.0",
                        "3.13",
                    ),
                    true,
                    Some(root.join("prefix/lib/libpython3.13.so.1.0")),
                )
            },
        },
    ];

    for test_case in test_cases {
        let (_directory, root) = temporary_root();
        let interpreter: PathBuf = (test_case.prepare)(&root);

        let found = locate_library(&interpreter);

        assert_eq!(
            found,
            (test_case.expected_located)(&root),
            "{}",
            test_case.description
        );
    }
}

#[cfg(unix)]
#[test]
fn given_interpreter_answers_when_no_library_is_in_the_usual_places_then_the_answer_decides() {
    let test_cases = [
        ProbeTestCase {
            description: "a static build runs by exec, cached until the interpreter changes",
            answer: &["0", "", "", "<root>/base", "3.12"],
            expected_located: |root| {
                located(
                    HostDiscovery::Exec(rooted(
                        "<root>/venv/bin/python has no shared libpython",
                        root,
                    )),
                    true,
                    None,
                )
            },
        },
        ProbeTestCase {
            description: "a shared library outside the installation is not used",
            answer: &[
                "1",
                "<root>/elsewhere",
                "libpython3.12.so.1.0",
                "<root>/base",
                "3.12",
            ],
            expected_located: |root| {
                located(
                    HostDiscovery::Exec(rooted(
                        "<root>/venv/bin/python has no shared libpython in its installation",
                        root,
                    )),
                    true,
                    Some(root.join("elsewhere/libpython3.12.so.1.0")),
                )
            },
        },
        ProbeTestCase {
            description: "a shared library in a custom directory of the installation",
            answer: &[
                "1",
                "<root>/base/custom",
                "libpython3.12.so.1.0",
                "<root>/base",
                "3.12",
            ],
            expected_located: |root| {
                located(
                    embeddable(
                        root,
                        "venv/bin/python",
                        "base/custom/libpython3.12.so.1.0",
                        "3.12",
                    ),
                    true,
                    Some(root.join("base/custom/libpython3.12.so.1.0")),
                )
            },
        },
        ProbeTestCase {
            description: "an unreadable answer is not cached",
            answer: &["garbage"],
            expected_located: |root| {
                located(
                    HostDiscovery::Exec(rooted(
                        "<root>/venv/bin/python described itself unexpectedly",
                        root,
                    )),
                    false,
                    None,
                )
            },
        },
    ];

    for test_case in test_cases {
        let (_directory, root) = temporary_root();
        touch(&root.join("elsewhere/libpython3.12.so.1.0"));
        touch(&root.join("base/custom/libpython3.12.so.1.0"));
        let interpreter: PathBuf = venv(&root, "version_info = 3.12");
        let answer: Vec<String> = test_case
            .answer
            .iter()
            .map(|line| rooted(line, &root))
            .collect();
        describing_interpreter(&interpreter, &root.join("runs"), &answer);

        let found = locate_library(&interpreter);

        assert_eq!(
            found,
            (test_case.expected_located)(&root),
            "{}",
            test_case.description
        );
    }
}
