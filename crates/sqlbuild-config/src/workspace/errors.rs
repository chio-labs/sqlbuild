//! Why a playground or skill install could not be written.

use std::io;
use std::path::PathBuf;
use std::str::Utf8Error;

/// A coded user error, a file that is not UTF-8 text, or an I/O failure.
#[derive(Debug)]
pub enum WorkspaceError {
    /// `CliUserError(message, code=code, help=help)`.
    User {
        code: &'static str,
        message: String,
        help: Option<String>,
    },
    /// A text file that does not decode as UTF-8.
    Decode {
        path: PathBuf,
        bytes: Vec<u8>,
        error: Utf8Error,
    },
    Io(io::Error),
}

impl WorkspaceError {
    pub(crate) fn user(code: &'static str, message: String, help: Option<&str>) -> Self {
        Self::User {
            code,
            message,
            help: help.map(str::to_owned),
        }
    }
}

impl From<io::Error> for WorkspaceError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}
