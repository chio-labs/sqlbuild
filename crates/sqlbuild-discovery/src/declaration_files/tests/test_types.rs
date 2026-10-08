use crate::declaration_files::models::{CollectionKind, CollectionRequest};

/// One in-memory declaration file and the outcome Python's parser produces for it.
pub(super) struct DeclarationTextTestCase {
    pub(super) description: &'static str,
    pub(super) kind: CollectionKind,
    pub(super) contents: &'static str,
    /// Fragments of the outcome's debug text: the variant, names, messages and bodies.
    pub(super) expected_fragments: &'static [&'static str],
}

/// A project read collection by collection through one discovery session.
pub(super) struct SessionReadTestCase {
    pub(super) description: &'static str,
    pub(super) files: &'static [(&'static str, &'static str)],
    pub(super) requests: &'static [CollectionRequest],
    pub(super) expected_counts: &'static [usize],
    /// The layouts walked: one shared by every kind, plus one per isolated kind.
    pub(super) expected_layouts: usize,
}

/// A declaration file whose header nests one value far too deeply, on header line `line`.
pub(super) struct DeepDeclarationTestCase {
    pub(super) description: &'static str,
    pub(super) kind: CollectionKind,
    /// The file text before the nested value.
    pub(super) prefix: &'static str,
    /// The file text after the nested value.
    pub(super) suffix: &'static str,
    /// The statement name and file line the failure reports.
    pub(super) expected_location: (&'static str, usize),
}
