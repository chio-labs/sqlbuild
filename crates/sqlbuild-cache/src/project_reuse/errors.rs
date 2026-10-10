//! Why a stored compile could not be recorded.

/// Recording failed; the stored compile for this slot was removed.
#[derive(Debug)]
pub struct ReuseRecordError {
    pub message: String,
}

impl From<std::io::Error> for ReuseRecordError {
    fn from(error: std::io::Error) -> Self {
        Self {
            message: error.to_string(),
        }
    }
}
