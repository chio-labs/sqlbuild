use crate::freshness::errors::FreshnessError;

/// Parses `YYYY-MM-DDTHH:MM` text the tests write.
pub(crate) struct MinuteParser;

pub(crate) struct EquivalenceTestCase {
    pub(crate) description: &'static str,
    pub(crate) previous: &'static str,
    pub(crate) current: &'static str,
    pub(crate) lag_tolerance: Option<&'static str>,
    pub(crate) expected_equivalent: Result<bool, FreshnessError>,
}
