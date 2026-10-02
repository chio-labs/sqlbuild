//! SQBRSQL043 ranking sort caps and SQBRSQL018 ranking determinism proofs.

use std::borrow::Cow;
use std::collections::{HashMap, HashSet};

use polyglot_sql::expressions::{Over, Select, WindowFunction};
use polyglot_sql::scope::walk_in_scope;
use polyglot_sql::tokens::Token;
use polyglot_sql::{Expression, ExpressionWalk};

use crate::configuration::main::setting_help::setting_help;
use crate::sql_lint::models::LintDiagnostic;
use crate::sql_quality::constants::{
    MAX_RANKING_ORDER_BY_KEY, RANKING_SORT_CAP, RANKING_SORT_GUIDANCE, RULES_THRESHOLDS_SECTION,
    TIE_SENSITIVE_FUNCTIONS, UNPROVEN_RANKING_MESSAGE, UNPROVEN_RANKING_REMEDIATION,
    UNSTABLE_ROW_NUMBER_CODE,
};
use crate::sql_quality::keys::{KeyEnvironment, covers, window_columns};
use crate::sql_quality::models::QualityRequest;
use crate::sql_quality::syntax::{columns, lower};
use crate::sql_quality::types::InputKey;

const PRIORITY_FIX_REFUSAL: &str =
    "Choosing a priority column and tie-breaker requires author intent";
const KEY_FIX_REFUSAL: &str = "Declaring a key or adding a tie-breaker requires author intent";

struct RankingWindow<'a> {
    function: &'static str,
    window: &'a WindowFunction,
    select: &'a Select,
}

pub(crate) fn diagnostics(
    request: &QualityRequest<'_>,
    environment: &KeyEnvironment,
) -> Vec<LintDiagnostic> {
    let cap: bool = request.enabled.contains(RANKING_SORT_CAP.code);
    let proof: bool = request.enabled.contains(UNSTABLE_ROW_NUMBER_CODE);
    let mut used: HashSet<usize> = HashSet::new();
    let mut function_tokens: HashMap<String, Vec<usize>> = HashMap::new();
    for (index, token) in request.tokens.iter().enumerate() {
        if TIE_SENSITIVE_FUNCTIONS
            .iter()
            .chain(["RANK", "DENSE_RANK"].iter())
            .any(|name| token.text.eq_ignore_ascii_case(name))
        {
            function_tokens
                .entry(token.text.to_ascii_uppercase())
                .or_default()
                .push(index);
        }
    }
    let mut found: Vec<LintDiagnostic> = Vec::new();
    for ranking in ranking_windows(request.statements) {
        let over: Option<&Over> = effective_over(&ranking.window.over, ranking.select);
        let order: Vec<&Expression> = over.map_or_else(Vec::new, |over| {
            over.order_by.iter().map(|ordered| &ordered.this).collect()
        });
        let partition: &[Expression] = over.map_or(&[], |over| over.partition_by.as_slice());
        let exceeds: bool = cap && order.len() > request.max_ranking_order_by;
        let unproven: bool = proof
            && !order.is_empty()
            && TIE_SENSITIVE_FUNCTIONS.contains(&ranking.function)
            && !proven(environment, ranking.select, partition, &order);
        if !exceeds && !unproven {
            continue;
        }
        let candidates: &[usize] = function_tokens
            .get(ranking.function)
            .map_or(&[], Vec::as_slice);
        let token: Option<usize> = function_token(
            request.tokens,
            candidates,
            window_anchor(partition, &order),
            &used,
        );
        let (start, end) = token.map_or((0, 0), |index| {
            (
                request.tokens[index].span.start,
                request.tokens[index].span.end,
            )
        });
        used.extend(token);
        if exceeds {
            found.push(LintDiagnostic {
                code: RANKING_SORT_CAP.code,
                message: RANKING_SORT_CAP.message,
                remediation: Cow::Owned(sort_cap_remediation(
                    order.len(),
                    request.max_ranking_order_by,
                )),
                start,
                end,
                fix: None,
                fix_unavailable_reason: Some(PRIORITY_FIX_REFUSAL),
            });
        }
        if unproven {
            found.push(LintDiagnostic {
                code: UNSTABLE_ROW_NUMBER_CODE,
                message: UNPROVEN_RANKING_MESSAGE,
                remediation: Cow::Borrowed(UNPROVEN_RANKING_REMEDIATION),
                start,
                end,
                fix: None,
                fix_unavailable_reason: Some(KEY_FIX_REFUSAL),
            });
        }
    }
    found
}

fn sort_cap_remediation(sort_keys: usize, limit: usize) -> String {
    format!(
        "{RANKING_SORT_GUIDANCE} {}",
        setting_help(
            &format!("To allow {sort_keys} sort keys (the current value is {limit})"),
            RULES_THRESHOLDS_SECTION,
            MAX_RANKING_ORDER_BY_KEY,
            &sort_keys.to_string(),
        )
    )
}

fn proven(
    environment: &KeyEnvironment,
    select: &Select,
    partition: &[Expression],
    order: &[&Expression],
) -> bool {
    let keys: Vec<InputKey> = environment.input_keys(select);
    covers(&keys, &window_columns(partition, order))
}

fn ranking_windows(statements: &[Expression]) -> Vec<RankingWindow<'_>> {
    let mut found: Vec<RankingWindow<'_>> = Vec::new();
    for statement in statements {
        for node in statement.dfs() {
            let Expression::Select(select) = node else {
                continue;
            };
            for local in walk_in_scope(node, false) {
                let Expression::WindowFunction(window) = local else {
                    continue;
                };
                let function: &'static str = match &window.this {
                    Expression::RowNumber(_) => "ROW_NUMBER",
                    Expression::Rank(_) => "RANK",
                    Expression::DenseRank(_) => "DENSE_RANK",
                    Expression::FirstValue(_) => "FIRST_VALUE",
                    Expression::LastValue(_) => "LAST_VALUE",
                    _ => continue,
                };
                found.push(RankingWindow {
                    function,
                    window,
                    select,
                });
            }
        }
    }
    found
}

fn effective_over<'a>(over: &'a Over, select: &'a Select) -> Option<&'a Over> {
    let mut current: &Over = over;
    let mut seen: HashSet<String> = HashSet::new();
    loop {
        if !current.order_by.is_empty() || current.window_name.is_none() {
            return Some(current);
        }
        let name: String = lower(&current.window_name.as_ref()?.name);
        if !seen.insert(name.clone()) {
            return None;
        }
        current = &select
            .windows
            .iter()
            .flatten()
            .find(|window| lower(&window.name.name) == name)?
            .spec;
    }
}

/// Start offset of the first located column a window partitions or orders by.
fn window_anchor(partition: &[Expression], order: &[&Expression]) -> Option<usize> {
    let mut expressions: Vec<&Expression> = partition.iter().collect();
    expressions.extend(order.iter().copied());
    for expression in expressions {
        for column in columns(expression) {
            if let Some(span) = column.span {
                return Some(span.start);
            }
        }
    }
    None
}

/// The function-name token before the anchor, or the first token not reported yet.
fn function_token(
    tokens: &[Token],
    candidates: &[usize],
    anchor: Option<usize>,
    used: &HashSet<usize>,
) -> Option<usize> {
    if let Some(anchor) = anchor {
        let before: usize = candidates.partition_point(|&index| tokens[index].span.start < anchor);
        if let Some(position) = before.checked_sub(1) {
            return Some(candidates[position]);
        }
    }
    candidates
        .iter()
        .copied()
        .find(|index| !used.contains(index))
}
