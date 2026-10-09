use crate::macro_arguments::types::ArgumentHost;

pub(crate) struct ParseMacroArgumentsTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) nested: &'static [(usize, usize)],
    /// The parse result spelled with `{:?}`.
    pub(crate) expected_plan: &'static str,
}

/// A host knowing one character name and NFKC-folding the `ﬁ` ligature, rejecting `€`.
pub(crate) struct TestHost;

impl ArgumentHost for TestHost {
    fn character_named(&self, name: &str) -> Option<char> {
        (name == "LATIN SMALL LETTER E WITH ACUTE").then_some('é')
    }

    fn identifier(&self, text: &str) -> Option<String> {
        (!text.contains('€')).then(|| text.replace('ﬁ', "fi"))
    }
}
