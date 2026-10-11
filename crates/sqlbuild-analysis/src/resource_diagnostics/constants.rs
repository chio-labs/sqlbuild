//! Fixed texts of the compile-input resource diagnostics.

pub(crate) const LINE_COMMENT_START: &str = "--";
pub(crate) const BLOCK_COMMENT_START: &str = "/*";
pub(crate) const BLOCK_COMMENT_END: &str = "*/";
pub(crate) const UNCLOSED_BLOCK_COMMENT: &str = "SQL contains an unclosed block comment";
pub(crate) const INCREMENTAL: &str = "incremental";
pub(crate) const ROLLING_WINDOW: &str = "rolling_window";
pub(crate) const RELATION_KINDS: [&str; 4] = ["ref", "source", "seed", "dbt_ref"];
pub(crate) const CURSOR_HELP: &str = "read the data through __ref(), __source() or __seed() so its cursor can bound the window, or use materialized table if the model has no upstream data";
