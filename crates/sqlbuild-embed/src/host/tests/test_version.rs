use crate::host::_helpers::version::check_version;
use crate::host::tests::test_types::VersionTestCase;

#[test]
fn given_reported_libpython_version_when_checking_then_only_matching_supported_releases_pass() {
    let test_cases = [
        VersionTestCase {
            description: "the venv's minor version",
            reported: "3.12.13 (main, Aug 24 2026, 18:51:00) [Clang 20.1.4 ]",
            version: "3.12",
            expected_accepted: true,
        },
        VersionTestCase {
            description: "the venv's exact release",
            reported: "3.14.7 (main, Oct 1 2026, 10:00:00) [GCC 13.3.0]",
            version: "3.14.7",
            expected_accepted: true,
        },
        VersionTestCase {
            description: "a pre-release reports only its minor version digits",
            reported: "3.14.0rc1 (main, Jul 1 2025, 10:00:00) [GCC 13.3.0]",
            version: "3.14.0",
            expected_accepted: true,
        },
        VersionTestCase {
            description: "another patch release than the venv records",
            reported: "3.12.12 (main, Aug 24 2026, 18:51:00) [GCC 13.3.0]",
            version: "3.12.13",
            expected_accepted: false,
        },
        VersionTestCase {
            description: "another minor version than the venv's",
            reported: "3.13.5 (main, Aug 24 2026, 18:51:00) [GCC 13.3.0]",
            version: "3.12",
            expected_accepted: false,
        },
        VersionTestCase {
            description: "an unsupported Python",
            reported: "3.11.12 (main, Aug 24 2026, 18:51:00) [GCC 13.3.0]",
            version: "3.11",
            expected_accepted: false,
        },
        VersionTestCase {
            description: "a free-threaded build",
            reported: "3.14.7 experimental free-threading build (main, Oct 1 2026) [GCC 13.3.0]",
            version: "3.14",
            expected_accepted: false,
        },
        VersionTestCase {
            description: "an unreadable version",
            reported: "unknown",
            version: "3.12",
            expected_accepted: false,
        },
    ];

    for test_case in test_cases {
        let checked = check_version(test_case.reported, test_case.version);

        assert_eq!(
            checked.is_ok(),
            test_case.expected_accepted,
            "{}",
            test_case.description
        );
    }
}
