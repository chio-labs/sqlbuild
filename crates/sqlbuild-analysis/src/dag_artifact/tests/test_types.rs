use crate::assembly::project::types::ObjectKey;
use crate::dag_artifact::errors::DagArtifactError;
use crate::dag_artifact::models::{DagProjectInput, DagPythonGraphInput};

pub(crate) struct BuildDagJsonTestCase {
    pub(crate) description: &'static str,
    pub(crate) project: DagProjectInput,
    pub(crate) python: Option<DagPythonGraphInput>,
    pub(crate) upstream: Vec<(ObjectKey, Vec<ObjectKey>)>,
    pub(crate) expected_json: Result<&'static str, DagArtifactError>,
}
