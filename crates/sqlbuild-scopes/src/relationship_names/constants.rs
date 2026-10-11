//! Fixed names the relationship scan reads.

pub(crate) const MODEL_MODE: &str = "model";
pub(crate) const MACRO_MODE: &str = "macro";
pub(crate) const MACRO_ACTUAL_CTE: &str = "__macro_actual__";
/// Declaration references, which macro call scans skip.
pub(crate) const DECLARATION_CALLS: [&str; 2] = ["enum", "const"];
