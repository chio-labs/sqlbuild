use crate::project_tree::errors::ProjectTreeFileError;

pub(crate) struct ProjectTreeEntriesTestCase {
    pub(crate) description: &'static str,
    pub(crate) expected_entries: Vec<(&'static str, bool)>,
}

pub(crate) struct ProjectTreeFileTestCase {
    pub(crate) description: &'static str,
    pub(crate) path: &'static str,
    /// The project-relative file read, or why none may be.
    pub(crate) expected_file: Result<&'static str, ProjectTreeFileError>,
}
