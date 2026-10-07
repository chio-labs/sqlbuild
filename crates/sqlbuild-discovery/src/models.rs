//! Results native discovery hands to the Python facade.

use sqlbuild_core::text::errors::TextDecodeError;
use std::path::PathBuf;

/// The Python `DiscoveryError` subclass a native failure is raised as.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FailureKind {
    /// `ModelSqlParseError` (D002).
    ModelSql,
    /// `DeclarationParseError` (D013).
    Declaration,
}

impl FailureKind {
    /// The stable name the facade maps to an exception class.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::ModelSql => "model_sql",
            Self::Declaration => "declaration",
        }
    }
}

/// One discovery failure with Python's exact message and optional help.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DiscoveryFailure {
    pub kind: FailureKind,
    pub message: String,
    pub help: Option<String>,
}

impl DiscoveryFailure {
    /// A failure without help text.
    pub fn new(kind: FailureKind, message: String) -> Self {
        Self {
            kind,
            message,
            help: None,
        }
    }
}

/// Native discovery cannot reproduce Python for this project; the Python stage runs instead.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StageDeferral {
    pub reason: String,
}

/// The outcome of reading and parsing one authored file.
#[derive(Clone, Debug, PartialEq)]
pub enum FileOutcome<T> {
    Parsed(T),
    Failed(DiscoveryFailure),
    /// The bytes could not be read or decoded; Python re-reads the file to raise its error.
    Unreadable,
}

/// One discovered file, by `/`-separated path relative to the project directory.
#[derive(Clone, Debug, PartialEq)]
pub struct DiscoveredFile<T> {
    pub relative_path: String,
    pub outcome: FileOutcome<T>,
}

/// A one-based line and code-point column range, as Python's `SourceLocation` stores it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LineColumnSpan {
    pub line: usize,
    pub column: usize,
    pub end_line: usize,
    pub end_column: usize,
}

/// The project directory and the text Python prints before a relative path (`str(project_dir / x)`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProjectRoot {
    pub directory: PathBuf,
    pub display_prefix: String,
}

impl ProjectRoot {
    /// Python's `str(project_dir / relative_path)` for a `/`-separated relative path.
    pub fn display_path(&self, relative_path: &str) -> String {
        format!("{}{relative_path}", self.display_prefix)
    }
}

/// Why an authored file could not be read the way Python's `read_text` reads it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReadFailure {
    Io(std::io::ErrorKind),
    Decode(TextDecodeError),
}
