//! What the parse asks of the interpreter it runs for.

use crate::argv::models::{TypeFailure, Value};

/// The interpreter-owned pieces of a parse: converters, `repr` and version.
pub trait ArgvHost {
    /// Apply the `type=` converter named `converter` to `text`.
    fn convert(&mut self, converter: &str, text: &str) -> Result<Value, TypeFailure>;
    /// Python's `repr` of a command-line string.
    fn repr(&self, text: &str) -> String;
    /// The installed `sqlbuild` version `--version` prints.
    fn program_version(&mut self) -> String;
}
