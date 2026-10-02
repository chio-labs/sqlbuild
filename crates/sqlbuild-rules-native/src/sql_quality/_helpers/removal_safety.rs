//! SQBRSQL042 allow-list: when removing an unused CTE output provably keeps every row.

use polyglot_sql::expressions::Select;
use polyglot_sql::traversal::contains_aggregate;
use polyglot_sql::{Expression, ExpressionWalk};

use crate::sql_quality::constants::{
    DETERMINISTIC_SCALAR_FUNCTIONS, MIN_REMOVABLE_OUTPUTS, ROW_NEUTRAL_EXPRESSIONS,
};

const ORDER_BY_ALL: &str = "all";
const DISTINCT_REFUSAL: &str = "SELECT DISTINCT depends on every output column";
const DISTINCT_ON_REFUSAL: &str = "SELECT DISTINCT ON keeps one row per key chosen by the select";
const GROUP_BY_ALL_REFUSAL: &str = "GROUP BY ALL groups by every non-aggregate output column";
const ORDER_BY_ALL_REFUSAL: &str = "ORDER BY ALL sorts by every output column";
const UNGROUPED_AGGREGATE_REFUSAL: &str =
    "An aggregate select without GROUP BY depends on its whole projection";
const POSITIONAL_REFUSAL: &str = "Positional GROUP BY or ORDER BY would shift";
const ONLY_OUTPUT_REFUSAL: &str = "Removing the only output column leaves an empty select";
const EXPRESSION_REFUSAL: &str = "Only column references and deterministic scalar expressions are removed automatically; this expression may change the rows the CTE returns";

/// Why removing any output of `select` could change its rows, if it could.
pub(super) fn select_refusal(select: &Select, outputs: usize) -> Option<&'static str> {
    if select.distinct {
        Some(DISTINCT_REFUSAL)
    } else if select.distinct_on.is_some() {
        Some(DISTINCT_ON_REFUSAL)
    } else if select
        .group_by
        .as_ref()
        .is_some_and(|group| group.all == Some(true))
    {
        Some(GROUP_BY_ALL_REFUSAL)
    } else if orders_by_all(select) {
        Some(ORDER_BY_ALL_REFUSAL)
    } else if select.group_by.is_none()
        && (select.having.is_some() || select.expressions.iter().any(contains_aggregate))
    {
        Some(UNGROUPED_AGGREGATE_REFUSAL)
    } else if positional_clauses(select) {
        Some(POSITIONAL_REFUSAL)
    } else if outputs < MIN_REMOVABLE_OUTPUTS {
        Some(ONLY_OUTPUT_REFUSAL)
    } else {
        None
    }
}

/// Why removing this one projection could change the rows, if it could.
pub(super) fn expression_refusal(expression: &Expression) -> Option<&'static str> {
    (!row_neutral(expression)).then_some(EXPRESSION_REFUSAL)
}

/// Whether a star select depends on every input column or on their positions.
pub(super) fn reads_whole_rows(select: &Select) -> bool {
    select.distinct
        || select.distinct_on.is_some()
        || select.group_by.is_some()
        || orders_by_all(select)
        || positional_clauses(select)
}

/// A column reference or deterministic scalar expression (no aggregate, window, SRF or subquery).
fn row_neutral(expression: &Expression) -> bool {
    expression.dfs().all(|node| match node {
        Expression::Function(function) => {
            let name: String = function.name.to_ascii_uppercase();
            !function.distinct && DETERMINISTIC_SCALAR_FUNCTIONS.contains(&name.as_str())
        }
        other => ROW_NEUTRAL_EXPRESSIONS.contains(&other.variant_name()),
    })
}

fn orders_by_all(select: &Select) -> bool {
    select
        .order_by
        .iter()
        .flat_map(|order| order.expressions.iter())
        .any(|ordered| {
            matches!(&ordered.this, Expression::Column(column)
                if column.table.is_none()
                    && !column.name.quoted
                    && column.name.name.eq_ignore_ascii_case(ORDER_BY_ALL))
        })
}

fn positional_clauses(select: &Select) -> bool {
    let numeric = |expression: &Expression| matches!(expression, Expression::Literal(_));
    select
        .group_by
        .iter()
        .flat_map(|group| group.expressions.iter())
        .any(numeric)
        || select
            .order_by
            .iter()
            .flat_map(|order| order.expressions.iter())
            .any(|ordered| numeric(&ordered.this))
}
