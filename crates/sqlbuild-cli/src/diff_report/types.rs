//! Tuple shapes of diff facts.

use crate::diff_report::models::DiffValue;

/// One named value, such as a key column of a sampled row.
pub type DiffNamedValue = (String, DiffValue);

/// A schema column whose type differs: name, `from` type and `to` type.
pub type DiffTypeChange = (String, String, String);
