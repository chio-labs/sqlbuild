//! What interpreter discovery found.

use std::path::PathBuf;

/// An interpreter whose shared libpython `sqb` can load and run in its own process.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EmbeddableInterpreter {
    /// The interpreter exactly as the Python CLI script starts it; CPython's `argv[0]`.
    pub interpreter: PathBuf,
    /// The shared libpython of the interpreter's installation.
    pub library: PathBuf,
    /// The version libpython must report: `3.12`, or `3.12.13` when the venv records it.
    pub version: String,
}

/// How `sqb` can start the Python CLI script it found.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum HostDiscovery {
    /// Load the interpreter's libpython and run the CLI in this process.
    Embeddable(EmbeddableInterpreter),
    /// Run the script as a program, for the stated reason.
    Exec(String),
}

/// Why a discovered interpreter could not be started in this process.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EmbedFailure {
    pub reason: String,
}

/// What discovery found for one interpreter, and how long the answer holds.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct LocatedHost {
    pub(crate) found: HostDiscovery,
    /// Whether the answer depends only on the interpreter's files and `watched`.
    pub(crate) cacheable: bool,
    /// A library file whose appearance, change or removal invalidates the answer.
    pub(crate) watched: Option<PathBuf>,
}
