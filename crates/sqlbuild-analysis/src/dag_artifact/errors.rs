//! Why the DAG artifact could not be built, named after the Python error each reproduces.

use sqlbuild_core::json::errors::JsonEmitError;

/// A failure building or encoding the DAG artifact.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DagArtifactError {
    /// `SpecConfigError` for a loader destination that is not 1 to 3 non-empty parts.
    LoaderDestination(String),
    /// `KeyError` for a bound SQL test parameter missing from the parameter schema.
    MissingParameterType(String),
    /// `TypeError` for the first value `json.dumps` cannot encode.
    Unencodable(String),
    /// The emitter refused the encoded artifact.
    Emit(JsonEmitError),
}
