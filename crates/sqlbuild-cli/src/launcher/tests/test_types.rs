use crate::launcher::_helpers::hosting::HostMode;

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

/// A `SQLBUILD_HOST_MODE` value and the host mode it selects, if any.
pub(crate) struct HostModeTestCase {
    pub(crate) description: &'static str,
    pub(crate) value: Option<&'static str>,
    pub(crate) expected_mode: Option<HostMode>,
}

/// The script and arguments handed to the Python CLI and the CPython arguments running them.
pub(crate) struct HostedArgumentsTestCase {
    pub(crate) description: &'static str,
    pub(crate) script: &'static str,
    pub(crate) handed: &'static [&'static str],
    pub(crate) expected_arguments: &'static [&'static str],
}
