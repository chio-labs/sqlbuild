//! Why a blank project could not be created.

use std::io;
use std::path::PathBuf;

/// The I/O failure and the path it happened at, as Python's `OSError` names its `filename`.
#[derive(Debug)]
pub struct ScaffoldError {
    pub error: io::Error,
    pub path: PathBuf,
}
