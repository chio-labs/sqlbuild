use std::collections::HashSet;

use polyglot_sql::expressions::{Over, Select};
use polyglot_sql::scope::walk_in_scope;
use polyglot_sql::tokens::Token;
use polyglot_sql::{Expression, ExpressionWalk};

use crate::sql_lint::models::{LintDiagnostic, LintRuleMetadata};

pub(super) const RANKING_SORT_CAP: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL043",
    message: "Ranking window exceeds max_ranking_order_by",
    remediation: "Long ranking sorts usually encode a priority. Compute a named priority column in an earlier CTE (CASE or a lookup seed), then order by that priority, the few meaningful sort columns, and a unique tie-breaker.",
};

pub(crate) fn default_limit() -> usize {
    4
}

pub(super) fn diagnostics(
    statements: &[Expression],
    tokens: &[Token],
    limit: usize,
) -> Vec<LintDiagnostic> {
    let mut findings: Vec<LintDiagnostic> = Vec::new();
    for statement in statements {
        for node in statement.dfs() {
            let Expression::Select(select) = node else {
                continue;
            };
            for local in walk_in_scope(node, false) {
                let Expression::WindowFunction(window) = local else {
                    continue;
                };
                let name = match &window.this {
                    Expression::RowNumber(_) => "ROW_NUMBER",
                    Expression::Rank(_) => "RANK",
                    Expression::DenseRank(_) => "DENSE_RANK",
                    Expression::FirstValue(_) => "FIRST_VALUE",
                    Expression::LastValue(_) => "LAST_VALUE",
                    _ => continue,
                };
                if order_count(&window.over, select) <= limit {
                    continue;
                }
                let span = tokens
                    .iter()
                    .find(|token| token.text.eq_ignore_ascii_case(name))
                    .map(|token| token.span);
                findings.push(LintDiagnostic {
                    code: RANKING_SORT_CAP.code,
                    message: RANKING_SORT_CAP.message.to_owned(),
                    remediation: RANKING_SORT_CAP.remediation,
                    start: span.map_or(0, |span| span.start),
                    end: span.map_or(0, |span| span.end),
                    fix: None,
                    fix_unavailable_reason: Some(
                        "Choosing priority columns and tie-breakers requires author intent",
                    ),
                });
            }
        }
    }
    findings
}

fn order_count(over: &Over, select: &Select) -> usize {
    let mut current = over;
    let mut seen: HashSet<String> = HashSet::new();
    loop {
        if !current.order_by.is_empty() {
            return current.order_by.len();
        }
        let Some(name) = &current.window_name else {
            return 0;
        };
        if !seen.insert(name.name.clone()) {
            return 0;
        }
        let Some(window) = select.windows.iter().flatten().find(|window| {
            if name.quoted || window.name.quoted {
                window.name.name == name.name
            } else {
                window.name.name.eq_ignore_ascii_case(&name.name)
            }
        }) else {
            return 0;
        };
        current = &window.spec;
    }
}
