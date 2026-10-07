pub(super) struct PositionTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) byte_offset: usize,
    pub(super) expected_position: Option<(usize, usize, usize)>,
}

pub(super) struct SpanTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) byte_range: (usize, usize),
    pub(super) expected_ends: Option<((usize, usize), (usize, usize))>,
}

pub(super) struct DecodeTestCase {
    pub(super) description: &'static str,
    pub(super) bytes: &'static [u8],
    pub(super) expected_text: Result<&'static str, usize>,
}

pub(super) struct CloseMatchesTestCase {
    pub(super) description: &'static str,
    pub(super) word: &'static str,
    pub(super) possibilities: &'static [&'static str],
    pub(super) count: usize,
    pub(super) cutoff: f64,
    pub(super) expected_matches: &'static [&'static str],
}

pub(super) struct CharacterClassTestCase {
    pub(super) description: &'static str,
    pub(super) character: char,
    pub(super) expected_alnum: bool,
    pub(super) expected_word: bool,
    pub(super) expected_space: bool,
}
