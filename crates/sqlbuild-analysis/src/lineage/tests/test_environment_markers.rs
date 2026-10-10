use crate::lineage::_helpers::environment_markers::environment_names;
use crate::lineage::tests::test_types::EnvironmentMarkerTestCase;

/// Python's `ENV:\s*([A-Za-z0-9_]+)` matches, `None` where it refuses to cache.
#[test]
fn given_environment_markers_when_scanning_then_matches_python_regex_and_checks() {
    let test_cases = [
        EnvironmentMarkerTestCase {
            description: "no markers",
            contents: b"SELECT 1",
            expected_names: Some(&[]),
        },
        EnvironmentMarkerTestCase {
            description: "names with spacing",
            contents: b"${ENV:A} ${ENV: \t\nB_2}",
            expected_names: Some(&["A", "B_2"]),
        },
        EnvironmentMarkerTestCase {
            description: "a marker without a name",
            contents: b"ENV: ",
            expected_names: None,
        },
        EnvironmentMarkerTestCase {
            description: "a name directly before a non-ASCII byte",
            contents: b"ENV:AB\xc3\x89",
            expected_names: None,
        },
        EnvironmentMarkerTestCase {
            description: "a marker inside a matched name",
            contents: b"ENV: ENV:X",
            expected_names: None,
        },
        EnvironmentMarkerTestCase {
            description: "a name ending the file",
            contents: b"x ENV:LAST",
            expected_names: Some(&["LAST"]),
        },
        EnvironmentMarkerTestCase {
            description: "a repeated name",
            contents: b"ENV:A ENV:A",
            expected_names: Some(&["A", "A"]),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            environment_names(test_case.contents).as_deref(),
            test_case.expected_names,
            "{}",
            test_case.description
        );
    }
}
