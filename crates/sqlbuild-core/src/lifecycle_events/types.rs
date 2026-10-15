//! The shape of one catalogue entry.

/// One catalogued event: type, required correlations, required and allowed payload, terminal.
pub(crate) type CatalogEntry = (
    &'static str,
    &'static [&'static str],
    &'static [&'static str],
    &'static [&'static str],
    bool,
);

/// One event-family payload rule: the first violation in a payload, if any.
pub(crate) type PayloadCheck =
    fn(&[(String, crate::lifecycle_events::models::PayloadValue)]) -> Option<String>;
