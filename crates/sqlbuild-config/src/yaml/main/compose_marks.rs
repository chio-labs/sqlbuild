//! Compose one YAML document, keeping each node's char-index marks in the original text.

use crate::constants::BYTE_ORDER_MARK;
use crate::errors::ConfigError;
use crate::models::{ComposedYaml, ComposedYamlContent, ComposedYamlNode};
use crate::yaml::models::{Node, NodeContent};

/// The composed nodes of `text`, with marks counted in chars of `text` itself.
pub fn compose_marks(text: &str) -> Result<ComposedYaml, ConfigError> {
    let shift = usize::from(text.starts_with(BYTE_ORDER_MARK));
    let text = crate::yaml::_helpers::reader::without_byte_order_mark(text);
    crate::yaml::_helpers::reader::check_characters(text)?;
    let document = crate::yaml::_helpers::composer::compose(text)?;
    Ok(ComposedYaml {
        nodes: document
            .nodes
            .into_iter()
            .map(|node| composed_node(node, shift))
            .collect(),
        root: document.root,
    })
}

fn composed_node(node: Node, shift: usize) -> ComposedYamlNode {
    ComposedYamlNode {
        start: node.span.0 + shift,
        end: node.span.1 + shift,
        content: match node.content {
            NodeContent::Scalar(value) => ComposedYamlContent::Scalar(value),
            NodeContent::Sequence(items) => ComposedYamlContent::Sequence(items),
            NodeContent::Mapping(entries) => ComposedYamlContent::Mapping(entries),
        },
    }
}
