#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct SqlTestFixtureFacts {
    pub(crate) mock: bool,
    pub(crate) empty_fixture_marker: bool,
}
