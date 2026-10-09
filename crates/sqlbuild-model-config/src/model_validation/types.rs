//! The outcome type native validation threads through every check.

use crate::model_validation::models::ValidationStop;

/// Validation's outcome: accepted, or the first problem.
pub type Check = Result<(), ValidationStop>;
