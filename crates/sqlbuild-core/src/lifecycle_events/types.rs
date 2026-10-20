//! The shape of one event-family payload rule.

/// One event-family payload rule: the first violation in a payload, if any.
pub(crate) type PayloadCheck =
    fn(&[(String, crate::lifecycle_events::models::PayloadValue)]) -> Option<String>;
