//! A column trace in the requested output format.

use sqlbuild_core::cli_text::models::CliStyle;

use crate::lineage_command::_helpers::column_text::{column_list, column_tree};
use crate::lineage_command::_helpers::json::trace_json;
use crate::lineage_command::constants::{JSON_OUTPUT_FORMAT, LIST_OUTPUT_FORMAT};
use crate::lineage_command::models::{ColumnTrace, LineageRendering};

/// JSON, a dependency list, or a tree from the traced column.
#[must_use]
pub fn render_column_trace(
    trace: &ColumnTrace,
    output_format: &str,
    style: CliStyle,
) -> LineageRendering {
    match output_format {
        JSON_OUTPUT_FORMAT => LineageRendering::Json(trace_json(trace)),
        LIST_OUTPUT_FORMAT => LineageRendering::Text(column_list(trace, style)),
        _ => LineageRendering::Text(column_tree(trace, style)),
    }
}
