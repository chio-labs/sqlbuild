//! Source line of one SQL-test fixture CTE definition.

use regex::Regex;

use crate::planner_fixtures::constants::FIXTURE_WHITESPACE;

/// Return the one-based line that starts a fixture CTE definition, or line one when absent.
pub fn fixture_line(contents: &str, cte_name: &str) -> Result<usize, regex::Error> {
    let pattern = Regex::new(&format!(
        r"(?im)^{FIXTURE_WHITESPACE}*{}{FIXTURE_WHITESPACE}+AS{FIXTURE_WHITESPACE}*\(",
        regex::escape(cte_name)
    ))?;
    Ok(pattern.find(contents).map_or(1, |found| {
        contents[..found.start()].matches('\n').count() + 1
    }))
}
