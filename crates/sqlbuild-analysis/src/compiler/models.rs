#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SqlTestFixtureFacts {
    pub mock: bool,
    pub empty_fixture_marker: bool,
}
