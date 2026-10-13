pub(super) struct LayerMoveTestCase {
    pub(super) description: &'static str,
    pub(super) old_path: &'static str,
    pub(super) new_name: &'static str,
    pub(super) codes: &'static [&'static str],
    pub(super) project_dir: Option<&'static str>,
    pub(super) windows: bool,
    pub(super) expected_command: Option<&'static str>,
    pub(super) expected_folder: Option<&'static str>,
}

pub(super) struct RenderTestCase {
    pub(super) description: &'static str,
    pub(super) old_path: &'static str,
    pub(super) new_name: &'static str,
    pub(super) codes: &'static [&'static str],
    pub(super) expected_text: &'static str,
}
