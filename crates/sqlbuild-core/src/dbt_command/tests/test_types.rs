use crate::dbt_command::models::{DbtOutputOptions, ForwardedArg};

pub(super) struct ArgsTestCase {
    pub(super) description: &'static str,
    pub(super) args: Vec<String>,
    pub(super) expected_options: DbtOutputOptions,
    pub(super) expected_forwarded: Vec<ForwardedArg>,
    pub(super) expected_target: Option<String>,
}

pub(super) struct RenderTestCase {
    pub(super) description: &'static str,
    pub(super) rendered: String,
    pub(super) expected_text: &'static str,
}
