//! Why the manifest could not be built or encoded, named after the Python error each reproduces.

use sqlbuild_core::json::errors::JsonEmitError;

/// A failure while building the manifest, raised where Python's builder raised it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ManifestError {
    /// `QueryFingerprintError` of a model query that cannot be fingerprinted.
    QueryFingerprint(String),
    /// `KeyError` for a bound SQL test parameter missing from the parameter schema.
    MissingParameterType(String),
}

/// A failure encoding the built manifest, raised where `json.dumps` raised it: on writing.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ManifestEncodeError {
    /// `TypeError` for the first value `json.dumps` cannot encode.
    Unencodable(String),
    /// The emitter refused the encoded manifest.
    Emit(JsonEmitError),
}
