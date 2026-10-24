use crate::sql_macros::_helpers::typed_calls::typed_sql;
use crate::sql_macros::models::{TextSplice, TypedCall};

/// `sql` with each call that declares `returns` wrapped in the analysis-only typed marker, and
/// each marker insertion as an empty source range of `sql`.
#[must_use]
pub fn typed_analysis_sql(sql: &str, calls: &[TypedCall]) -> (String, Vec<TextSplice>) {
    typed_sql(sql, calls)
}
