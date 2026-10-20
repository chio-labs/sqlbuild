use crate::config_values::models::{ConfigNode, HostChildren, HostFacts, HostValue};
use crate::config_values::tests::test_types::Node;
use crate::types::NodeKind;

/// A string node.
pub(super) fn text(value: &str) -> Node {
    ConfigNode::Str(value.to_owned())
}

/// A `StrEnum`-like host value whose text is `value`.
pub(super) fn host_text(value: &str) -> Node {
    ConfigNode::Host(HostValue {
        handle: 1,
        facts: HostFacts {
            kind: NodeKind::Str,
            text: Some(value.to_owned()),
            strict_text: true,
            integer: None,
            number: None,
            python_str: value.to_owned(),
            strict_str: true,
            python_repr: format!("<Severity.WARN: '{value}'>"),
            date_like: false,
            hook_entry: false,
        },
        children: HostChildren::None,
    })
}

/// A list of string nodes.
pub(super) fn texts(values: &[&str]) -> Node {
    ConfigNode::List(values.iter().map(|value| text(value)).collect())
}
