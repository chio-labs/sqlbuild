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
