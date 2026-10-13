//! The positional `FROM[:TO]` target range of `sqb diff`.

use crate::diff_report::_helpers::request_rules::user_error;
use crate::diff_report::errors::DiffUserError;

/// `FROM:TO` or a bare `FROM`, which leaves `TO` unset.
pub fn parse_diff_name_range(range: &str) -> Result<(String, Option<String>), DiffUserError> {
    let (from_name, to_name): (&str, Option<&str>) = match range.split_once(':') {
        Some((from_name, to_name)) => (from_name, Some(to_name)),
        None => (range, None),
    };
    if from_name.is_empty()
        || to_name.is_some_and(|to_name| to_name.is_empty() || to_name.contains(':'))
    {
        return Err(user_error("diff range must be FROM:TO or FROM", "C209"));
    }
    Ok((from_name.to_owned(), to_name.map(str::to_owned)))
}
