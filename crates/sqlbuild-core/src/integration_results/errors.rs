//! A record that violates the integration-result contract.

use std::fmt;

/// The contract an integration-result record or value broke, as Python's `ObservabilityValidationError` said it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct IntegrationRecordError {
    pub message: String,
}

impl IntegrationRecordError {
    pub(crate) fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for IntegrationRecordError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}
