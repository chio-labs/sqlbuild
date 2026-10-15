//! The shape of one catalogue entry.

/// One catalogued event: type, required correlations, required and allowed payload, terminal.
pub(crate) type CatalogEntry = (
    &'static str,
    &'static [&'static str],
    &'static [&'static str],
    &'static [&'static str],
    bool,
);
