//! Compose one YAML document the way PyYAML's `yaml.compose` does, keeping node marks.

use crate::constants::BYTE_ORDER_MARK;
use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::{ComposedYaml, ComposedYamlContent, ComposedYamlNode};
use crate::yaml::models::NodeContent;

/// PyYAML's safe `yaml.compose` nodes with char-index marks; anchors and tags are `Unsupported`.
pub fn compose_marks(text: &str) -> Result<ComposedYaml, ConfigError> {
    let shift = usize::from(text.starts_with(BYTE_ORDER_MARK));
    let text = crate::yaml::_helpers::reader::without_byte_order_mark(text);
    crate::yaml::_helpers::reader::check_characters(text)?;
    let document = crate::yaml::_helpers::composer::compose(text)?;
    if document.nodes.iter().any(|node| node.decorated) {
        return Err(ConfigError::new(
            ConfigErrorKind::Unsupported,
            "marks of nodes with an anchor or a tag",
        ));
    }
    Ok(ComposedYaml {
        nodes: document
            .nodes
            .into_iter()
            .map(|node| ComposedYamlNode {
                content: match node.content {
                    NodeContent::Scalar(value) => ComposedYamlContent::Scalar(value),
                    NodeContent::Sequence(items) => ComposedYamlContent::Sequence(items),
                    NodeContent::Mapping(entries) => ComposedYamlContent::Mapping(entries),
                },
                start: node.span.0 + shift,
                end: node.span.1 + shift,
            })
            .collect(),
        root: document.root,
    })
}
