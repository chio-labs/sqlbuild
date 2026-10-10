//! Expected refactoring failures and the Python exception each becomes.

use serde::Serialize;

/// Which Python exception an expected refactoring failure becomes.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RefactorErrorKind {
    /// `RefactorInputError`: the request cannot be planned.
    Input,
    /// `RefactorEditError`: two planned edits overlap.
    Edit,
    /// `RefactorWriteError`: project files changed while the refactoring ran.
    Write,
    /// An internal native failure, raised as `NativeCompilerError`.
    Internal,
    /// A `ValueError` the Python planner does not handle, such as a header the tokenizer rejects.
    Value,
    /// An `OSError` reading or writing project files, which Python does not handle either.
    Io,
}

/// An expected refactoring failure with Python's code, message and help.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct RefactorError {
    pub kind: RefactorErrorKind,
    pub code: String,
    pub message: String,
    pub help: Option<String>,
}

impl RefactorError {
    /// A `RefactorInputError` with an explicit code.
    pub fn input(code: &str, message: impl Into<String>, help: Option<&str>) -> Self {
        Self {
            kind: RefactorErrorKind::Input,
            code: code.to_owned(),
            message: message.into(),
            help: help.map(str::to_owned),
        }
    }

    /// An unhandled `ValueError` with Python's message.
    pub fn value(message: String) -> Self {
        Self {
            kind: RefactorErrorKind::Value,
            code: String::new(),
            message,
            help: None,
        }
    }

    /// An internal native failure with the reason native code stopped.
    pub fn internal(message: impl Into<String>) -> Self {
        Self {
            kind: RefactorErrorKind::Internal,
            code: String::new(),
            message: message.into(),
            help: None,
        }
    }
}
