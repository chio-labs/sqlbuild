//! `query_history_sql`: the Snowflake `QUERY_HISTORY` read of one end-time window.

use crate::cost_allocation::constants::{NULL_QUERY_TEXT, QUERY_HISTORY_FUNCTION};
use crate::cost_allocation::models::QueryHistoryWindow;

fn query_history_function(database: Option<&str>) -> String {
    match database {
        None => QUERY_HISTORY_FUNCTION.to_owned(),
        Some(database) => format!(
            "\"{}\".{QUERY_HISTORY_FUNCTION}",
            database.to_uppercase().replace('"', "\"\"")
        ),
    }
}

fn query_text_expression(query_ids: &[String]) -> String {
    if query_ids.is_empty() {
        return NULL_QUERY_TEXT.to_owned();
    }
    let mut sorted: Vec<&String> = query_ids.iter().collect();
    sorted.sort();
    sorted.dedup();
    let literals: Vec<String> = sorted
        .into_iter()
        .map(|query_id| format!("'{}'", query_id.replace('\'', "''")))
        .collect();
    format!(
        "CASE WHEN QUERY_ID IN ({}) AND (QUERY_TYPE = 'CREATE' OR QUERY_TYPE LIKE 'CREATE_%') \
THEN QUERY_TEXT END AS QUERY_TEXT",
        literals.join(", ")
    )
}

/// Query-history SQL for queries ending after `start`, and before `end` when it is bounded.
pub fn query_history_sql(window: &QueryHistoryWindow<'_>) -> String {
    let end_range: String = match window.end {
        Some(end) => format!("\n  END_TIME_RANGE_END => TO_TIMESTAMP_LTZ('{end}'),"),
        None => String::new(),
    };
    format!(
        "SELECT
  QUERY_ID,
  QUERY_TAG,
  WAREHOUSE_NAME,
  WAREHOUSE_SIZE,
  WAREHOUSE_TYPE,
  CLUSTER_NUMBER,
  START_TIME,
  END_TIME,
  EXECUTION_TIME,
  BYTES_SCANNED,
  EXECUTION_STATUS,
  QUERY_TYPE,
  {},
  CURRENT_TIMESTAMP()
FROM TABLE({}(
  END_TIME_RANGE_START => TO_TIMESTAMP_LTZ('{}'),{end_range}
  RESULT_LIMIT => {}
))
ORDER BY START_TIME, QUERY_ID",
        query_text_expression(window.classification_query_ids),
        query_history_function(window.database),
        window.start,
        window.result_limit,
    )
}
