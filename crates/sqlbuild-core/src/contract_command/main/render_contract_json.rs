//! The contract comparison as sorted, indented JSON.

use crate::contract_command::_helpers::json_document::{resource, text};
use crate::contract_command::models::ContractReport;
use crate::json::errors::JsonEmitError;
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

/// `json.dumps(payload, indent=2, sort_keys=True)` of the report, and a newline.
pub fn render_contract_json(report: &ContractReport) -> Result<String, JsonEmitError> {
    let differences: JsonInteger =
        JsonInteger::from(u64::try_from(report.difference_count()).unwrap_or(u64::MAX));
    let document: JsonValue = JsonValue::Object(vec![
        ("from_target".to_owned(), text(&report.from_target)),
        ("differences".to_owned(), JsonValue::Integer(differences)),
        (
            "written_paths".to_owned(),
            JsonValue::Array(report.written_paths.iter().map(|path| text(path)).collect()),
        ),
        (
            "resources".to_owned(),
            JsonValue::Array(report.resources.iter().map(resource).collect()),
        ),
    ]);
    let mut options: StdlibJsonOptions = StdlibJsonOptions::new(Some(2));
    options.sort_keys = true;
    Ok(format!(
        "{}\n",
        dumps(&document, &JsonDialect::Stdlib(options))?
    ))
}
