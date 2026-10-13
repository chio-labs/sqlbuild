//! A selected relation graph in the requested output format.

use sqlbuild_core::cli_text::models::CliStyle;

use crate::lineage_command::_helpers::graph_text::{graph_list, graph_tree};
use crate::lineage_command::_helpers::json::graph_json;
use crate::lineage_command::constants::{JSON_OUTPUT_FORMAT, LIST_OUTPUT_FORMAT};
use crate::lineage_command::models::{LineageGraph, LineageRendering};

/// JSON, an edge list, or a tree around the focus node.
#[must_use]
pub fn render_lineage_graph(
    graph: &LineageGraph,
    output_format: &str,
    style: CliStyle,
) -> LineageRendering {
    match output_format {
        JSON_OUTPUT_FORMAT => LineageRendering::Json(graph_json(graph)),
        LIST_OUTPUT_FORMAT => LineageRendering::Text(graph_list(graph, style)),
        _ => LineageRendering::Text(graph_tree(graph, style)),
    }
}
