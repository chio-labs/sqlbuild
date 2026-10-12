//! The native failure of reading a macro module CPython accepted.

use std::fmt;

/// The ruff parser rejected a module that CPython parsed.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MacroModuleParseError {
    pub relative_path: String,
    pub message: String,
}

impl fmt::Display for MacroModuleParseError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "Native macro module analysis cannot parse '{}', which CPython accepted: {}",
            self.relative_path, self.message
        )
    }
}

impl std::error::Error for MacroModuleParseError {}

/// Why one strict analysis of a set of macro modules stopped.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum MacroAnalysisFailure {
    /// The message of the `CompileInputError` Python's analysis raised first.
    Compile(String),
    Native(MacroModuleParseError),
}
