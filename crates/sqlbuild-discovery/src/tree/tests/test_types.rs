pub(super) struct GlobTestCase {
    pub(super) description: &'static str,
    pub(super) files: &'static [&'static str],
    pub(super) directories: &'static [&'static str],
    /// Symbolic links as `(link, target)`, both relative to the project.
    pub(super) links: &'static [(&'static str, &'static str)],
    pub(super) suffix: &'static str,
    pub(super) expected_paths: &'static [&'static str],
}

pub(super) struct PathOrderTestCase {
    pub(super) description: &'static str,
    pub(super) case_insensitive: bool,
    pub(super) paths: &'static [&'static str],
    pub(super) expected_paths: &'static [&'static str],
}

pub(super) struct WindowsErrnoTestCase {
    pub(super) description: &'static str,
    pub(super) winerror: i32,
    pub(super) expected_errno: i32,
}

pub(super) struct OsFailureTestCase {
    pub(super) description: &'static str,
    pub(super) code: Option<i32>,
    pub(super) message: &'static str,
    pub(super) windows: bool,
    pub(super) expected_errno: Option<i32>,
    pub(super) expected_winerror: Option<i32>,
    pub(super) expected_message: &'static str,
}

/// Files written by raw byte path below a project whose `models/` is walked for `*.sql`.
#[cfg(unix)]
pub(super) struct UndecodableWalkTestCase {
    pub(super) description: &'static str,
    pub(super) files: &'static [&'static [u8]],
    pub(super) expected_paths: &'static [&'static str],
    pub(super) expected_failures: &'static [Option<&'static str>],
    /// `file N` for the Nth written file, in walk order.
    pub(super) expected_contents: &'static [&'static str],
}

/// A junction `models/linked` to a directory holding `orders.sql`, walked for `*.sql`.
#[cfg(windows)]
pub(super) struct JunctionWalkTestCase {
    pub(super) description: &'static str,
    pub(super) expected_paths: &'static [&'static str],
}

pub(super) struct RawSegmentTestCase {
    pub(super) description: &'static str,
    pub(super) segment: &'static str,
    pub(super) expected_display: &'static str,
    pub(super) expected_code_points: &'static [u32],
}

pub(super) struct WideUnitsTestCase {
    pub(super) description: &'static str,
    pub(super) units: &'static [u32],
    pub(super) expected_code_points: &'static [u32],
}
