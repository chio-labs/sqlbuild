//! Compose one YAML document the way PyYAML's `yaml.compose` does, keeping node marks.

use crate::constants::BYTE_ORDER_MARK;
use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::{ComposedYaml, ComposedYamlContent, ComposedYamlNode};
use crate::yaml::_helpers::anchors::{code_ends, properties_start};
use crate::yaml::models::{Node, NodeContent};

/// PyYAML's safe `yaml.compose` nodes; scalar marks are PyYAML's char-index marks.
pub fn compose_marks(text: &str) -> Result<ComposedYaml, ConfigError> {
    let shift = usize::from(text.starts_with(BYTE_ORDER_MARK));
    let text = crate::yaml::_helpers::reader::without_byte_order_mark(text);
    crate::yaml::_helpers::reader::check_characters(text)?;
    let document = crate::yaml::_helpers::composer::compose(text)?;
    let chars: Vec<char> = text.chars().collect();
    let ends: Vec<usize> = code_ends(&chars);
    let nodes: Vec<ComposedYamlNode> = document
        .nodes
        .into_iter()
        .map(|node| composed_node(node, (&chars, &ends), shift))
        .collect::<Result<_, _>>()?;
    Ok(ComposedYaml {
        nodes,
        root: document.root,
    })
}

fn composed_node(
    node: Node,
    source: (&[char], &[usize]),
    shift: usize,
) -> Result<ComposedYamlNode, ConfigError> {
    let (chars, ends) = source;
    let start = properties_start(chars, ends, node.span.0, node.properties).ok_or_else(|| {
        ConfigError::new(
            ConfigErrorKind::Unsupported,
            "node properties PyYAML marks differently",
        )
    })?;
    Ok(ComposedYamlNode {
        content: match node.content {
            NodeContent::Scalar(value) => ComposedYamlContent::Scalar(value),
            NodeContent::Sequence(items) => ComposedYamlContent::Sequence(items),
            NodeContent::Mapping(entries) => ComposedYamlContent::Mapping(entries),
        },
        start: start + shift,
        end: node.span.1 + shift,
    })
}
