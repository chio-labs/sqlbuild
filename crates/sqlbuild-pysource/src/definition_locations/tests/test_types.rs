pub(super) struct DecoratorLocationTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) python_version: (u8, u8),
    pub(super) expected_location: (usize, usize),
}
