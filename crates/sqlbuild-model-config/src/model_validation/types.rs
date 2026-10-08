//! The outcome type native validation threads through every check.

use crate::model_validation::models::ValidationStop;

/// Native validation's outcome: accepted, the first Python error, or a deferral to Python.
pub type Check = Result<(), ValidationStop>;
