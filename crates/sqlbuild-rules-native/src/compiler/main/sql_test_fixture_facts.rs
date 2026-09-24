use crate::compiler::_helpers::sql_tests::{extraction, planning};
use crate::compiler::models::SqlTestFixtureFacts;

pub(crate) fn fixture_facts(name: &str, sql: &str) -> SqlTestFixtureFacts {
    SqlTestFixtureFacts {
        mock: planning::MOCK_CTE_PREFIXES.iter().any(|prefix| {
            name.strip_prefix(prefix)
                .is_some_and(|target| !target.is_empty())
        }),
        empty_fixture_marker: matches!(extraction::empty_fixture_marker_matches(sql), Ok(true)),
    }
}
