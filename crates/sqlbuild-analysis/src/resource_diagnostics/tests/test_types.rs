use crate::resource_diagnostics::models::HeaderHelp;

pub(crate) struct HeaderOffsetTestCase {
    pub(crate) description: &'static str,
    pub(crate) contents: &'static str,
    pub(crate) expected_offset: Result<usize, &'static str>,
}

pub(crate) struct MissingDescriptionTestCase {
    pub(crate) description: &'static str,
    pub(crate) authored: Option<&'static str>,
    pub(crate) expected_message: Option<&'static str>,
}

pub(crate) struct CursorInputsTestCase {
    pub(crate) description: &'static str,
    pub(crate) materialized: Option<&'static str>,
    pub(crate) microbatch_strategy: Option<&'static str>,
    pub(crate) has_cursor_inputs: bool,
    pub(crate) reference_kinds: &'static [&'static str],
    pub(crate) expected_lacks: bool,
}

pub(crate) struct HelpTestCase {
    pub(crate) description: &'static str,
    pub(crate) help: HeaderHelp<'static>,
    pub(crate) expected_help: &'static str,
}

pub(crate) struct YamlHelpTestCase {
    pub(crate) description: &'static str,
    /// Kind, name and path.
    pub(crate) entry: (&'static str, &'static str, &'static str),
    pub(crate) expected_help: &'static str,
}
