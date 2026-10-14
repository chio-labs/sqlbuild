pub(super) struct ArgvsTestCase {
    pub(super) description: &'static str,
    pub(super) argvs: Vec<Vec<String>>,
    pub(super) expected_argvs: Vec<Vec<&'static str>>,
}

pub(super) struct TextsTestCase {
    pub(super) description: &'static str,
    pub(super) texts: Vec<Option<String>>,
    pub(super) expected_texts: Vec<Option<&'static str>>,
}
