//! Cases for Dagster invocation assembly.

use crate::dagster_invocation::models::AssetFailure;

pub(super) struct ArgumentsTestCase {
    pub description: &'static str,
    pub args: Vec<&'static str>,
    pub expected_explicit_scenario: bool,
    pub expected_json_requested: bool,
    pub expected_json_path: Option<&'static str>,
}

pub(super) struct OrderTestCase {
    pub description: &'static str,
    pub ids: Vec<&'static str>,
    pub edges: Vec<(&'static str, &'static str)>,
    pub expected_order: Option<Vec<usize>>,
}

pub(super) struct CheckNameTestCase {
    pub description: &'static str,
    pub value: &'static str,
    pub expected_name: &'static str,
}

pub(super) struct WrapTestCase {
    pub description: &'static str,
    pub selectors: Vec<&'static str>,
    pub width: usize,
    pub expected_lines: Vec<&'static str>,
}

pub(super) struct FailureTextTestCase {
    pub description: &'static str,
    pub failure: AssetFailure,
    pub expected_text: &'static str,
}

pub(super) struct NameNormalizationTestCase {
    pub description: &'static str,
    pub value: &'static str,
    pub expected_tag_key: &'static str,
    pub expected_segment: &'static str,
}

pub(super) struct DescriptionTestCase {
    pub description: &'static str,
    pub text: &'static str,
    pub sql: Option<&'static str>,
    pub path: Option<&'static str>,
    pub expected_description: &'static str,
}

pub(super) struct FallbackDescriptionTestCase {
    pub description: &'static str,
    pub kind: &'static str,
    pub name: &'static str,
    pub qualified_name: &'static str,
    pub materialization: Option<&'static str>,
    pub expected_description: &'static str,
}
