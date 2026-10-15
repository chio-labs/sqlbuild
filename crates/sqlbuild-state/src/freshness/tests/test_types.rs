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

pub(crate) struct RelevantSourcesTestCase {
    pub(crate) description: &'static str,
    pub(crate) source_names: &'static [&'static str],
    pub(crate) expected_sql: &'static str,
}

pub(crate) struct SingleValueTestCase {
    pub(crate) description: &'static str,
    pub(crate) shape: crate::freshness::models::QueryShape,
    pub(crate) expected_problem: Option<&'static str>,
}

pub(crate) struct ConfigurationErrorTestCase {
    pub(crate) description: &'static str,
    pub(crate) message: &'static str,
    pub(crate) expected_configuration_error: bool,
}

pub(crate) struct ReadLatestTestCase {
    pub(crate) description: &'static str,
    pub(crate) qualified_name: &'static str,
    pub(crate) expected_sql: &'static str,
}
