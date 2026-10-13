use crate::dbt_manifest::errors::ManifestError;
use crate::dbt_manifest::models::{ManifestNode, ParsedModel};

pub(super) struct ModelTestCase {
    pub(super) description: &'static str,
    pub(super) node: ManifestNode,
    pub(super) expected_result: Result<ParsedModel, ManifestError>,
}
