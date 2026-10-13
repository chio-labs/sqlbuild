pub(super) struct TargetLineageTestCase {
    pub(super) description: &'static str,
    pub(super) targets: Vec<String>,
    pub(super) output_format: &'static str,
    pub(super) direction: &'static str,
    pub(super) depth: Option<i64>,
    pub(super) expected_stdout: Result<&'static str, &'static str>,
}

pub(super) struct ResolveTargetTestCase {
    pub(super) description: &'static str,
    pub(super) target: &'static str,
    pub(super) expected_name: Result<&'static str, &'static str>,
}
