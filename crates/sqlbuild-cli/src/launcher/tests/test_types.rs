/// Command-line arguments and where the launch record for them is looked up.
pub(crate) struct LaunchRecordPathTestCase {
    pub(crate) description: &'static str,
    pub(crate) arguments: &'static [&'static str],
    pub(crate) expected_project: Option<&'static str>,
}

/// One invocation keyed beside `sqb compile` in `/work`.
pub(crate) struct LaunchKeyTestCase {
    pub(crate) description: &'static str,
    pub(crate) arguments: &'static [&'static str],
    pub(crate) cwd: &'static str,
    pub(crate) expected_same: bool,
}
