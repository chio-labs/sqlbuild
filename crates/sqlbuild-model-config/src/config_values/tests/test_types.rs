use crate::config_values::models::ConfigNode;

/// A config node in tests; host handles are plain numbers.
pub(super) type Node = ConfigNode<u8>;

pub(super) struct PythonTextTestCase {
    pub(super) description: &'static str,
    pub(super) value: Node,
    pub(super) expected_str: &'static str,
    pub(super) expected_repr: &'static str,
}

pub(super) struct LayeredConfigTestCase {
    pub(super) description: &'static str,
    pub(super) base: Vec<(Node, Node)>,
    pub(super) overlay: Vec<(Node, Node)>,
    pub(super) expected_entries: Vec<(Node, Node)>,
    pub(super) expected_unioned_keys: Vec<&'static str>,
}

pub(super) struct ConfigEntryTestCase {
    pub(super) description: &'static str,
    pub(super) entries: Vec<(Node, Node)>,
    pub(super) key: &'static str,
    pub(super) expected_value: Option<Node>,
}

/// One config value and how each typed reader reads it: `value`, `none`, or the expected kind.
pub(super) struct CheckedReadTestCase {
    pub(super) description: &'static str,
    pub(super) value: Option<Node>,
    pub(super) expected_text: &'static str,
    pub(super) expected_flag: &'static str,
    pub(super) expected_integer: &'static str,
    pub(super) expected_texts: &'static str,
    pub(super) expected_cursor_bound: &'static str,
}
