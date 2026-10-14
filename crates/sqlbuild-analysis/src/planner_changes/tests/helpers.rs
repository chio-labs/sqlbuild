use crate::planner_changes::models::{
    Backfill, BackfillAction, NameSpan, SchemaChangeKind, SchemaColumnSource, SchemaFindingRow,
};

pub(super) fn backfill(action: BackfillAction, duration: Option<&str>) -> Backfill {
    Backfill {
        action,
        duration: duration.map(str::to_owned),
    }
}

pub(super) fn finding(
    (kind, name, source): (SchemaChangeKind, &str, SchemaColumnSource),
    expected_type: Option<&str>,
    actual_type: Option<&str>,
) -> SchemaFindingRow {
    SchemaFindingRow {
        kind,
        column_name: name.to_owned(),
        source,
        expected_type: expected_type.map(str::to_owned),
        actual_type: actual_type.map(str::to_owned),
    }
}

pub(super) fn pairs(items: &[(&str, &str)]) -> Vec<(String, String)> {
    items
        .iter()
        .map(|(left, right)| ((*left).to_owned(), (*right).to_owned()))
        .collect()
}

/// Case-insensitive type equality, as a stand-in for the adapter's type normalization.
pub(super) fn types_equal(left: &str, right: &str) -> Result<bool, ()> {
    Ok(left.eq_ignore_ascii_case(right))
}

/// The span of the one quoted `name` in an ASCII query.
pub(super) fn quoted_span(query_sql: &str, name: &str) -> NameSpan {
    let start: usize = query_sql.find(&format!("\"{name}\"")).unwrap_or_default() + 1;
    NameSpan {
        start,
        end: start + name.len(),
        name: name.to_owned(),
    }
}
