pub(crate) struct HintTestCase {
    pub(crate) description: &'static str,
    pub(crate) paths: Vec<&'static str>,
    pub(crate) expected_hint: Option<&'static str>,
}

pub(crate) struct ResultTestCase {
    pub(crate) description: &'static str,
    pub(crate) json_output: bool,
    pub(crate) expected_text: &'static str,
}
