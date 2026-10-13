//! The manifest bytes `json.dumps(manifest, indent=2) + "\n"` wrote, or the error encoding raised.

use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::graph::models::ProjectGraph;
use crate::manifest::_helpers::payload::payload;
use crate::manifest::constants::MANIFEST_INDENT;
use crate::manifest::errors::{ManifestEncodeError, ManifestError};
use crate::manifest::models::ManifestInput;
use crate::python_values::main::encode_python_value::encode_python_value;

/// Build the manifest; its encoding outcome is kept for the writer, where `json.dumps` raised.
pub fn build_manifest_json(
    input: &ManifestInput,
    graph: &ProjectGraph,
) -> Result<Result<String, ManifestEncodeError>, ManifestError> {
    let manifest = payload(input, graph)?;
    Ok(encode_python_value(manifest)
        .map_err(ManifestEncodeError::Unencodable)
        .and_then(|value: JsonValue| {
            dumps(
                &value,
                &JsonDialect::Stdlib(StdlibJsonOptions::new(Some(MANIFEST_INDENT))),
            )
            .map_err(ManifestEncodeError::Emit)
        })
        .map(|text| text + "\n"))
}
