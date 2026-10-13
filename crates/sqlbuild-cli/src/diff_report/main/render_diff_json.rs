//! The structured diff document, serialized as `json.dumps(indent=2, sort_keys=True)`.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, StdlibJsonOptions};

use crate::diff_report::_helpers::payload::document;
use crate::diff_report::models::{DiffDocumentOptions, DiffModelFacts};

/// The diff document text, without a trailing newline.
pub fn render_diff_json(
    models: &[DiffModelFacts],
    options: &DiffDocumentOptions,
) -> Result<String, JsonEmitError> {
    let mut settings: StdlibJsonOptions = StdlibJsonOptions::new(Some(2));
    settings.sort_keys = true;
    settings.allow_nan = false;
    dumps(&document(models, options), &JsonDialect::Stdlib(settings))
}
