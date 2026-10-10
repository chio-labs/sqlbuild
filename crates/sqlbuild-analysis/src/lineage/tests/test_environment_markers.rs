use crate::lineage::_helpers::environment_markers::environment_names;

/// Python's `ENV:\s*([A-Za-z0-9_]+)` matches, `None` where it refuses to cache.
#[test]
fn given_environment_markers_when_scanning_then_matches_python_regex_and_checks() {
    let test_cases: [(&str, &[u8], Option<&[&str]>); 7] = [
        ("no markers", b"SELECT 1", Some(&[])),
        ("names with spacing", b"${ENV:A} ${ENV: \t\nB_2}", Some(&["A", "B_2"])),
        ("a marker without a name", b"ENV: ", None),
        ("a name directly before a non-ASCII byte", b"ENV:AB\xc3\x89", None),
        ("a marker inside a matched name", b"ENV: ENV:X", None),
        ("a name ending the file", b"x ENV:LAST", Some(&["LAST"])),
        ("a repeated name", b"ENV:A ENV:A", Some(&["A", "A"])),
    ];
    for (description, contents, expected) in test_cases {
        assert_eq!(
            environment_names(contents).as_deref(),
            expected,
            "{description}"
        );
    }
}
