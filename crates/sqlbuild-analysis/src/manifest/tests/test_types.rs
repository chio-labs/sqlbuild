use crate::manifest::errors::{ManifestEncodeError, ManifestError};
use crate::manifest::models::ManifestInput;

pub(crate) struct BuildManifestJsonTestCase {
    pub(crate) description: &'static str,
    pub(crate) input: ManifestInput,
    pub(crate) expected_fragments: Vec<&'static str>,
}

pub(crate) struct ManifestFailureTestCase {
    pub(crate) description: &'static str,
    pub(crate) input: ManifestInput,
    /// The building error, or the encoding error kept for the writer.
    pub(crate) expected_error: Result<Option<ManifestEncodeError>, ManifestError>,
}
