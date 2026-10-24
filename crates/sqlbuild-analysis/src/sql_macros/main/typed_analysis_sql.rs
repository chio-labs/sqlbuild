use crate::sql_macros::_helpers::typing::typed_calls::{markable_calls, typed_sql};
use crate::sql_macros::models::{TextSplice, TypedCall};

/// `sql` with its typed calls wrapped in analysis-only markers, and each marker insertion.
#[must_use]
pub fn typed_analysis_sql(
    sql: &str,
    calls: &[TypedCall],
    dialect: &str,
) -> (String, Vec<TextSplice>) {
    typed_sql(sql, &markable_calls(sql, calls, dialect))
}
