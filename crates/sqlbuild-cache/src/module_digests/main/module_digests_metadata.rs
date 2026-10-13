//! The store metadata that records each module file's content digest.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::module_digests::_helpers::python_code_points::python_code_points;
use crate::module_digests::types::RowKey;

/// `json.dumps(sorted([path, digest] for path, digest in rows))`.
pub fn module_digests_metadata(rows: Vec<(JsonValue, JsonValue)>) -> Result<String, JsonEmitError> {
    let mut keyed: Vec<(RowKey, JsonValue)> = rows
        .into_iter()
        .map(|(path, digest)| {
            (
                (python_code_points(&path), python_code_points(&digest)),
                JsonValue::Array(vec![path, digest]),
            )
        })
        .collect();
    keyed.sort_by(|left, right| left.0.cmp(&right.0));
    dumps(
        &JsonValue::Array(keyed.into_iter().map(|(_, row)| row).collect()),
        &JsonDialect::Stdlib(StdlibJsonOptions::new(None)),
    )
}
