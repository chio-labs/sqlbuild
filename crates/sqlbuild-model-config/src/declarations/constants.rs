//! Declaration option names, scalar SQL types and rendering choices.

pub(crate) const VALUE_OPTION: &str = "value";
pub(crate) const TYPE_OPTION: &str = "type";
pub(crate) const RENDER_AS_OPTION: &str = "render_as";
pub(crate) const WRAPPER_OPTIONS: [&str; 3] = ["value", "type", "render_as"];
pub(crate) const VARCHAR_TYPE: &str = "VARCHAR";
pub(crate) const INTEGER_TYPE: &str = "INTEGER";
/// `CollectionRendering` values.
pub(crate) const COLLECTION_RENDERINGS: [&str; 2] = ["value_list", "array"];
