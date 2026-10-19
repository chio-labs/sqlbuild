//! Why an input cannot become a Recall record.

/// A rejected record input, with a message naming the problem.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RecordError {
    pub message: String,
}

impl RecordError {
    pub(crate) fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl std::fmt::Display for RecordError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for RecordError {}
