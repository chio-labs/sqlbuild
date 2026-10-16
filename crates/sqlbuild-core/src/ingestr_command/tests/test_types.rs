pub(super) struct DestinationUriTestCase {
    pub(super) description: &'static str,
    pub(super) adapter_name: &'static str,
    pub(super) strings: &'static [(&'static str, &'static str)],
    pub(super) port: Option<&'static str>,
    pub(super) expected_uri: Result<&'static str, &'static str>,
}

pub(super) struct CommandTestCase {
    pub(super) description: &'static str,
    pub(super) schema: Option<&'static str>,
    pub(super) is_reload: bool,
    pub(super) expected_display: &'static str,
}
