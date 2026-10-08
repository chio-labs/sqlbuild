//! The outcome type native validation threads through every check.

use crate::model_validation::models::Rejected;

/// Native validation's outcome; any rejection re-runs the Python validators.
pub type Check = Result<(), Rejected>;
