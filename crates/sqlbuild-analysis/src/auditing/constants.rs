//! Audit identity payload keys and the severity that blocks a gate.

/// The severity whose audits make up a gate's blocking set.
pub(crate) const BLOCKING_SEVERITY: &str = "error";
pub(crate) const MEASUREMENT_MODE: &str = "measurement";
pub(crate) const OUTSIDE_OPERATOR: &str = "outside";
pub(crate) const BELOW_OPERATOR: &str = "below";
pub(crate) const ABOVE_OPERATOR: &str = "above";
