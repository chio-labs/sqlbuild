use crate::config_values::errors::ConfigTypeError;
use crate::config_values::models::{ConfigNode, CursorBound, HostChildren, HostFacts, HostValue};
use crate::config_values::tests::test_types::Node;
use crate::types::NodeKind;

/// A string node.
pub(super) fn text(value: &str) -> Node {
    ConfigNode::Str(value.to_owned())
}

/// A `StrEnum`-like host value whose text is `value`.
pub(super) fn host_text(value: &str) -> Node {
    ConfigNode::Host(Box::new(HostValue {
        handle: 1,
        facts: HostFacts {
            kind: NodeKind::Str,
            text: Some(value.to_owned()),
            strict_text: true,
            integer: None,
            number: None,
        },
        children: HostChildren::None,
    }))
}

/// A list of string nodes.
pub(super) fn texts(values: &[&str]) -> Node {
    ConfigNode::List(values.iter().map(|value| text(value)).collect())
}

/// A `datetime.date` host value.
pub(super) fn host_date() -> Node {
    ConfigNode::Host(Box::new(HostValue {
        handle: 2,
        facts: HostFacts {
            kind: NodeKind::Other,
            text: None,
            strict_text: false,
            integer: None,
            number: None,
        },
        children: HostChildren::None,
    }))
}

/// `value`, `none`, or the expected kind of a typed read's outcome.
pub(super) fn outcome<T>(result: Result<Option<T>, ConfigTypeError<'_, u8>>) -> String {
    result.map_or_else(
        |error| error.expected.to_owned(),
        |value| value.map_or("none", |_| "value").to_owned(),
    )
}

/// `dated`, `stringified`, `none`, or the expected kind of a cursor bound read.
pub(super) fn cursor_outcome(
    result: Result<Option<CursorBound<'_, u8>>, ConfigTypeError<'_, u8>>,
) -> String {
    result.map_or_else(
        |error| error.expected.to_owned(),
        |bound| {
            let kinds = [
                ("dated", matches!(bound, Some(CursorBound::Dated(_)))),
                (
                    "stringified",
                    matches!(bound, Some(CursorBound::Stringified(_))),
                ),
            ];
            kinds
                .iter()
                .find(|(_, found)| *found)
                .map_or("none", |(kind, _)| kind)
                .to_owned()
        },
    )
}
