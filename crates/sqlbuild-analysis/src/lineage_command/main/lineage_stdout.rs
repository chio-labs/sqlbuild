//! The text `sqb lineage` writes to stdout.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::lineage_command::_helpers::json::use_json;
use crate::lineage_command::models::{LineageRendering, SemanticUse};

/// The rendering, followed by direct semantic uses when they were requested.
pub fn lineage_stdout(
    rendering: LineageRendering,
    uses: Option<&[SemanticUse]>,
) -> Result<String, JsonEmitError> {
    let dialect: JsonDialect = JsonDialect::Stdlib(StdlibJsonOptions::new(Some(2)));
    match (rendering, uses) {
        (LineageRendering::Json(value), None) => Ok(format!("{}\n", dumps(&value, &dialect)?)),
        (LineageRendering::Text(text), None) => Ok(format!("\n{text}\n\n")),
        (LineageRendering::Json(value), Some(uses)) => {
            let mut entries: Vec<(String, JsonValue)> = match value {
                JsonValue::Object(entries) => entries,
                _ => Vec::new(),
            };
            entries.push((
                "semantic_uses".to_owned(),
                JsonValue::Array(uses.iter().map(use_json).collect()),
            ));
            Ok(format!(
                "{}\n",
                dumps(&JsonValue::Object(entries), &dialect)?
            ))
        }
        (LineageRendering::Text(text), Some(uses)) => {
            let mut lines: Vec<String> = vec![
                String::new(),
                text,
                String::new(),
                "Direct semantic column uses".to_owned(),
            ];
            if uses.is_empty() {
                lines.push("  none".to_owned());
            }
            lines.extend(uses.iter().map(|semantic_use| {
                format!(
                    "  {} [{}] {}:{}.{} <- {}",
                    semantic_use.consumer_model,
                    semantic_use.context,
                    semantic_use.source.resource_type,
                    semantic_use.source.resource_name,
                    semantic_use.source.column_name,
                    semantic_use.expression
                )
            }));
            Ok(format!("{}\n\n", lines.join("\n")))
        }
    }
}
