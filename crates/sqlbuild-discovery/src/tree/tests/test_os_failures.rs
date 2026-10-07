use crate::_helpers::reading::{os_listing_failure, os_read_failure, windows_errno};
use crate::models::ReadFailure;
use crate::tree::tests::test_types::{OsFailureTestCase, WindowsErrnoTestCase};

#[test]
fn given_win32_errors_when_mapping_then_errno_matches_cpython_winerror_to_errno() {
    let test_cases = [
        WindowsErrnoTestCase {
            description: "access denied is EACCES",
            winerror: 5,
            expected_errno: 13,
        },
        WindowsErrnoTestCase {
            description: "a sharing violation is EACCES",
            winerror: 32,
            expected_errno: 13,
        },
        WindowsErrnoTestCase {
            description: "a missing path is ENOENT",
            winerror: 3,
            expected_errno: 2,
        },
        WindowsErrnoTestCase {
            description: "a missing file is ENOENT",
            winerror: 2,
            expected_errno: 2,
        },
        WindowsErrnoTestCase {
            description: "a file name that is not a directory is ENOTDIR",
            winerror: 267,
            expected_errno: 20,
        },
        WindowsErrnoTestCase {
            description: "a FACILITY_WIN32 HRESULT unwraps to its error",
            winerror: 0x8007_0005_u32.cast_signed(),
            expected_errno: 13,
        },
        WindowsErrnoTestCase {
            description: "a Winsock access error is its errno",
            winerror: 10013,
            expected_errno: 13,
        },
        WindowsErrnoTestCase {
            description: "an unmapped error is EINVAL",
            winerror: 1234,
            expected_errno: 22,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            windows_errno(test_case.winerror),
            test_case.expected_errno,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_os_errors_when_reading_then_each_platform_matches_python() {
    let test_cases = [
        OsFailureTestCase {
            description: "a POSIX read keeps its errno",
            code: Some(13),
            message: "Permission denied (os error 13)",
            windows: false,
            expected_errno: Some(13),
            expected_winerror: None,
            expected_message: "Permission denied (os error 13)",
        },
        OsFailureTestCase {
            description: "a Windows read reports the C runtime errno",
            code: Some(32),
            message: "The process cannot access the file. (os error 32)",
            windows: true,
            expected_errno: Some(13),
            expected_winerror: None,
            expected_message: "The process cannot access the file. (os error 32)",
        },
        OsFailureTestCase {
            description: "a read without a code keeps only its message",
            code: None,
            message: "stream did not contain valid UTF-8",
            windows: true,
            expected_errno: None,
            expected_winerror: None,
            expected_message: "stream did not contain valid UTF-8",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            os_read_failure(
                test_case.code,
                test_case.message.to_owned(),
                test_case.windows
            ),
            ReadFailure::Io {
                errno: test_case.expected_errno,
                winerror: test_case.expected_winerror,
                message: test_case.expected_message.to_owned(),
            },
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_listing_errors_when_reporting_then_windows_keeps_the_win32_error() {
    let test_cases = [
        OsFailureTestCase {
            description: "a POSIX listing keeps its errno",
            code: Some(13),
            message: "Permission denied (os error 13)",
            windows: false,
            expected_errno: Some(13),
            expected_winerror: None,
            expected_message: "Permission denied (os error 13)",
        },
        OsFailureTestCase {
            description: "a Windows listing keeps the Win32 error and the bare system message",
            code: Some(5),
            message: "Access is denied. (os error 5)",
            windows: true,
            expected_errno: None,
            expected_winerror: Some(5),
            expected_message: "Access is denied",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            os_listing_failure(
                test_case.code,
                test_case.message.to_owned(),
                test_case.windows
            ),
            ReadFailure::Io {
                errno: test_case.expected_errno,
                winerror: test_case.expected_winerror,
                message: test_case.expected_message.to_owned(),
            },
            "{}",
            test_case.description
        );
    }
}
