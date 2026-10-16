//! Cases for janitor planning decisions.

use crate::janitor_planning::models::{ArchiveTimestamp, OriginKey};

pub(super) struct ParseArchiveNameTestCase {
    pub description: &'static str,
    pub name: &'static str,
    pub expected_parts: Option<(ArchiveTimestamp, &'static str)>,
}

pub(super) struct BuildArchiveNameTestCase {
    pub description: &'static str,
    pub original_name: &'static str,
    pub identifier_limit: i64,
    pub kind: Option<&'static str>,
    pub expected_name: Result<&'static str, &'static str>,
}

pub(super) struct AddressingTestCase {
    pub description: &'static str,
    pub names: Vec<&'static str>,
    pub name: &'static str,
    pub expected_reason: Option<&'static str>,
}

pub(super) struct ExcludePatternTestCase {
    pub description: &'static str,
    pub name: &'static str,
    pub display_name: &'static str,
    pub patterns: Vec<String>,
    pub expected_pattern: Option<&'static str>,
}

pub(super) struct OriginKeysTestCase {
    pub description: &'static str,
    pub raw: &'static str,
    pub schemas: Vec<(Option<String>, Option<String>)>,
    pub expected_keys: Vec<OriginKey>,
}

pub(super) struct RequestMatchTestCase {
    pub description: &'static str,
    pub request: &'static str,
    pub expected_matches: bool,
}

pub(super) struct ArtifactNameTestCase {
    pub description: &'static str,
    pub name: &'static str,
    pub expected_parts: Option<(&'static str, &'static str)>,
}

pub(super) struct ArtifactNameBuildTestCase {
    pub description: &'static str,
    pub run_id: &'static str,
    pub side: &'static str,
    pub expected_parts: Option<(&'static str, &'static str)>,
}

pub(super) struct RetentionTestCase {
    pub description: &'static str,
    pub override_days: Option<i64>,
    pub configured: Option<i64>,
    pub expected_days: i64,
}
