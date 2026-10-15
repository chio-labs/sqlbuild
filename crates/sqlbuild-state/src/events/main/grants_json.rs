//! `grants_json`: the stored text of the grant statements copied to an old-name view.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

/// `json.dumps(list(grants))`, or `None` when grants were not recorded.
pub fn grants_json(grants: Option<&[String]>) -> Result<Option<String>, JsonEmitError> {
    let Some(grants) = grants else {
        return Ok(None);
    };
    let value = JsonValue::Array(grants.iter().cloned().map(JsonValue::String).collect());
    dumps(&value, &JsonDialect::Stdlib(StdlibJsonOptions::new(None))).map(Some)
}
