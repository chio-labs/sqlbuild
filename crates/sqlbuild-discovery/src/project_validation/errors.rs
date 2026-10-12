//! Errors of reading seed CSV headers the way Python's `csv` module does.

use crate::models::ReadFailure;

/// A `TypeError` or `ValueError` Python's `csv` module raises for a reader's settings.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CsvDialectError {
    pub class: String,
    pub message: String,
}

/// Why the header could not be read.
#[derive(Debug)]
pub(crate) enum HeaderError {
    Read(ReadFailure),
    /// `_csv.Error` with its message.
    Csv(String),
}

impl std::fmt::Display for HeaderError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Read(failure) => write!(formatter, "{failure:?}"),
            Self::Csv(message) => formatter.write_str(message),
        }
    }
}
