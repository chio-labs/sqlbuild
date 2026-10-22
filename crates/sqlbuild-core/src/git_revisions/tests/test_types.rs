pub(crate) struct SinceReferenceTestCase {
    pub(crate) description: &'static str,
    pub(crate) value: &'static str,
    pub(crate) configured: Option<&'static str>,
    /// The resolved ref, or the error code.
    pub(crate) expected_reference: Result<&'static str, &'static str>,
}

pub(crate) struct GitBaseTestCase {
    pub(crate) description: &'static str,
    pub(crate) project_directory: &'static str,
    pub(crate) reference: &'static str,
    pub(crate) expected_prefix: &'static str,
}

pub(crate) struct GitBaseFailureTestCase {
    pub(crate) description: &'static str,
    pub(crate) reference: &'static str,
    pub(crate) expected_code: &'static str,
    pub(crate) expected_message_fragment: &'static str,
    pub(crate) expected_help_fragment: &'static str,
}

pub(crate) struct ExportTreeTestCase {
    pub(crate) description: &'static str,
    pub(crate) relative_path: &'static str,
    pub(crate) expected_exported: Option<&'static str>,
    pub(crate) expected_working_tree: Option<&'static str>,
}

pub(crate) struct AbsentProjectTestCase {
    pub(crate) description: &'static str,
    pub(crate) project_prefix: &'static str,
    pub(crate) expected_exported: bool,
}

pub(crate) struct DependencyFilesTestCase {
    pub(crate) description: &'static str,
    pub(crate) reference: &'static str,
    pub(crate) expected_base: Vec<(&'static str, &'static str)>,
    pub(crate) expected_current: Vec<(&'static str, &'static str)>,
}
