//! Native TOML nesting limits.

/// The deepest inline nesting read natively; `tomllib` exhausts Python's recursion limit by 497.
pub(crate) const MAX_CONTAINER_DEPTH: u32 = 512;
/// Inline containers at this depth are read as separate values, under the parser's own limit.
pub(crate) const SPLIT_CONTAINER_DEPTH: usize = 64;
/// The key a separately read value is assigned to.
pub(crate) const SPLIT_VALUE_KEY: &str = "value";
/// Bracket depth past which a document is read on a thread with a larger stack.
pub(crate) const DEEP_DOCUMENT_BRACKETS: usize = 128;
/// The stack of that thread: the recursive parser needs more than a default thread has.
pub(crate) const DEEP_DOCUMENT_STACK_BYTES: usize = 64 * 1024 * 1024;
