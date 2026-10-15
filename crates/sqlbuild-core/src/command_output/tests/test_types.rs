/// One text and the result of a text operation on it.
pub(crate) struct TextTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected_parts: &'static [&'static str],
}

/// Fragments appended to one dispatcher buffer and the record messages they produce.
pub(crate) struct BufferingTestCase {
    pub(crate) description: &'static str,
    pub(crate) max_record_bytes: i64,
    pub(crate) fragments: &'static [&'static str],
    pub(crate) expected_messages: &'static [&'static str],
    pub(crate) expected_partial: &'static str,
}
