pub(super) struct CapturedProcessTestCase {
    pub(super) description: &'static str,
    pub(super) script: &'static str,
    pub(super) expected_returncode: i64,
    pub(super) expected_stdout: &'static str,
    pub(super) expected_stderr: &'static str,
}

pub(super) struct StreamedProcessTestCase {
    pub(super) description: &'static str,
    pub(super) script: &'static str,
    pub(super) target_path: Option<&'static str>,
    pub(super) expected_lines: Vec<&'static str>,
    pub(super) expected_returncode: i64,
}

pub(super) struct LaunchFailureTestCase {
    pub(super) description: &'static str,
    pub(super) program: &'static str,
    pub(super) expected_kind: std::io::ErrorKind,
}

pub(super) struct StopProcessTestCase {
    pub(super) description: &'static str,
    pub(super) script: &'static str,
    pub(super) settle: std::time::Duration,
    pub(super) expected_terminate_requests: usize,
}
