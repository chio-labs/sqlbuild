#[cfg(unix)]
use crate::project_tree::errors::{ProjectTreeFileError, RelativePartsError};

#[cfg(unix)]
pub(crate) struct ProjectTreeEntriesTestCase {
    pub(crate) description: &'static str,
    pub(crate) expected_entries: Vec<(&'static str, bool)>,
}

#[cfg(unix)]
pub(crate) struct ProjectTreeFileTestCase {
    pub(crate) description: &'static str,
    pub(crate) path: &'static str,
    /// The project-relative file read, or why none may be.
    pub(crate) expected_file: Result<&'static str, ProjectTreeFileError>,
}

pub(crate) struct PathSelectionTestCase {
    pub(crate) description: &'static str,
    pub(crate) argument: Option<&'static str>,
    pub(crate) expected_children: Vec<&'static str>,
    pub(crate) expected_descendants: Vec<&'static str>,
    pub(crate) expected_glob: Vec<&'static str>,
}

#[cfg(unix)]
pub(crate) struct RelativePartsTestCase {
    pub(crate) description: &'static str,
    pub(crate) path: &'static str,
    pub(crate) resolved: &'static str,
    pub(crate) under: Option<&'static str>,
    pub(crate) expected_parts: Result<Vec<&'static str>, RelativePartsError<()>>,
}

pub(crate) struct TrackedTextTestCase {
    pub(crate) description: &'static str,
    pub(crate) path: &'static str,
    pub(crate) expected_tracked: bool,
}

#[cfg(unix)]
pub(crate) struct EscapesTestCase {
    pub(crate) description: &'static str,
    pub(crate) path: &'static str,
    pub(crate) expected_escapes: bool,
}
