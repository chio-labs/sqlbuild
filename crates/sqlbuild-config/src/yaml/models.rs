//! The composed node graph of one YAML document, before construction.

/// The content of one node; aliases share node ids.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum NodeContent {
    Scalar(String),
    Sequence(Vec<usize>),
    Mapping(Vec<(usize, usize)>),
}

/// One node with its resolved tag, as PyYAML's composer produces it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Node {
    pub(crate) tag: String,
    pub(crate) content: NodeContent,
    /// The one-based line and column where the node starts.
    pub(crate) position: (usize, usize),
    /// The char indices where the node's token starts and ends, as the parser marks them.
    pub(crate) span: (usize, usize),
    /// Whether the node carries an anchor or a tag, which moves PyYAML's start mark onto them.
    pub(crate) decorated: bool,
}

/// A composed document; `root` is `None` for an empty stream.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct ComposedDocument {
    pub(crate) nodes: Vec<Node>,
    pub(crate) root: Option<usize>,
}
