use crate::query_facts::models::{ModelShape, ParsedFixture};

/// Parse a stubbed SQL-test fixture as one query.
pub(crate) fn parse_fixture(shape: ModelShape, dialect: &str) -> Result<ParsedFixture, String> {
    crate::query_facts::_helpers::facts::parse_fixture(shape, dialect)
}
