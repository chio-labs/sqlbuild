use crate::header_strings::models::{HeaderQuote, TripleQuoteError};

pub(crate) struct FoldTestCase {
    pub(crate) description: &'static str,
    pub(crate) written: &'static str,
    pub(crate) expected: &'static str,
}

pub(crate) struct TripleEndTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected: Result<(usize, usize), TripleQuoteError>,
}

pub(crate) struct QuotedEndTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected: Option<usize>,
}

pub(crate) struct ProseTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected: Result<(HeaderQuote, &'static str), &'static str>,
}

pub(crate) struct QuoteFailureTestCase {
    pub(crate) description: &'static str,
    pub(crate) error: &'static str,
    pub(crate) header: &'static str,
    pub(crate) expected: Option<(usize, usize, &'static str)>,
}
