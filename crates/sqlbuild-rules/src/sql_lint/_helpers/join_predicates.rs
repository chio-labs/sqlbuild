//! Join predicates, and whether an explicit cross join can multiply rows.

use std::borrow::Cow;
use std::collections::{HashMap, HashSet};

use polyglot_sql::expressions::{Expression, JoinKind, Literal, Select, Subquery, TableRef, With};
use polyglot_sql::parser::{Parser, ParserConfig};
use polyglot_sql::tokens::{Span, Token, TokenType};
use polyglot_sql::{DialectType, ExpressionWalk};

use crate::constants::SETTING_SNIPPET_INDENT;
use crate::sql_lint::constants::{
    CROSS_JOIN_CTE_MARKER, CROSS_JOIN_PATH_PLACEHOLDER, CROSS_JOIN_PREFIX,
    CROSS_JOIN_REASON_PLACEHOLDER, CROSS_JOIN_SUFFIX, CROSS_JOIN_UNNAMED_MESSAGE,
};
use crate::sql_lint::models::{CrossJoinRequest, LintDiagnostic, LintRuleMetadata};

const CROSS_JOIN_FIX_REASON: &str = "a keyed relationship requires user intent";
const FIRST_ROW: &str = "1";
const ROW_GENERATOR_FUNCTIONS: [&str; 16] = [
    "unnest",
    "explode",
    "explode_outer",
    "posexplode",
    "posexplode_outer",
    "inline",
    "inline_outer",
    "flatten",
    "generate_series",
    "generate_subscripts",
    "json_each",
    "json_tree",
    "json_array_elements",
    "jsonb_array_elements",
    "range",
    "stack",
];

pub(super) fn join_expression_spans(
    tokens: &[Token],
    depths: &[usize],
    dialect: DialectType,
) -> Vec<Span> {
    let mut spans: Vec<Span> = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        if token.token_type != TokenType::On {
            continue;
        }
        let clause = (0..index).rev().find(|&previous| {
            depths[previous] == depths[index]
                && matches!(
                    tokens[previous].token_type,
                    TokenType::Join
                        | TokenType::Select
                        | TokenType::Where
                        | TokenType::From
                        | TokenType::On
                )
        });
        if clause.is_none_or(|previous| tokens[previous].token_type != TokenType::Join) {
            continue;
        }
        let end = (index + 1..tokens.len())
            .find(|&next| {
                depths[next] < depths[index]
                    || (depths[next] == depths[index]
                        && matches!(
                            tokens[next].token_type,
                            TokenType::Join
                                | TokenType::Where
                                | TokenType::Group
                                | TokenType::Having
                                | TokenType::Qualify
                                | TokenType::Order
                                | TokenType::Limit
                                | TokenType::Union
                                | TokenType::Intersect
                                | TokenType::Except
                                | TokenType::Semicolon
                        ))
            })
            .unwrap_or(tokens.len());
        let mut parser = Parser::with_config(
            tokens[index + 1..end].to_vec(),
            ParserConfig {
                dialect: Some(dialect),
                ..Default::default()
            },
        );
        if !matches!(parser.parse_expressions(), Ok(Some(ref predicate)) if plain_predicate(predicate))
        {
            spans.push(token.span);
        }
    }
    spans
}

fn plain_column(expression: &Expression) -> bool {
    matches!(
        expression,
        Expression::Column(_) | Expression::Identifier(_)
    ) || matches!(expression, Expression::Paren(value) if plain_column(&value.this))
}

fn literal(expression: &Expression) -> bool {
    matches!(
        expression,
        Expression::Literal(_) | Expression::Boolean(_) | Expression::Null(_)
    ) || matches!(expression, Expression::Neg(value) if matches!(&value.this, Expression::Literal(_)))
}

fn operand(expression: &Expression) -> bool {
    plain_column(expression) || literal(expression)
}

fn comparison(left: &Expression, right: &Expression) -> bool {
    operand(left) && operand(right)
}

fn plain_predicate(expression: &Expression) -> bool {
    match expression {
        Expression::Boolean(_) => true,
        Expression::Paren(value) => plain_predicate(&value.this),
        Expression::And(value) | Expression::Or(value) => {
            plain_predicate(&value.left) && plain_predicate(&value.right)
        }
        Expression::Eq(value)
        | Expression::Neq(value)
        | Expression::Lt(value)
        | Expression::Lte(value)
        | Expression::Gt(value)
        | Expression::Gte(value)
        | Expression::NullSafeEq(value)
        | Expression::NullSafeNeq(value)
        | Expression::Adjacent(value)
        | Expression::ArrayContainsAll(value)
        | Expression::ArrayContainedBy(value)
        | Expression::ArrayOverlaps(value)
        | Expression::ExtendsLeft(value)
        | Expression::ExtendsRight(value)
        | Expression::Match(value)
        | Expression::TsMatch(value) => comparison(&value.left, &value.right),
        Expression::Like(value) | Expression::ILike(value) => {
            comparison(&value.left, &value.right)
                && value.escape.as_ref().is_none_or(literal)
                && value.quantifier.is_none()
        }
        Expression::Between(value) => {
            plain_column(&value.this) && operand(&value.low) && operand(&value.high)
        }
        Expression::In(value) => {
            plain_column(&value.this)
                && value.query.is_none()
                && value.unnest.is_none()
                && !value.is_field
                && !value.expressions.is_empty()
                && value.expressions.iter().all(literal)
        }
        Expression::IsNull(value) => plain_column(&value.this),
        _ => false,
    }
}

/// A `rule` diagnostic for every cross join that can multiply rows, naming its relation and CTE.
pub(super) fn cross_join_diagnostics(
    request: &CrossJoinRequest<'_>,
    rule: &LintRuleMetadata,
) -> Vec<LintDiagnostic> {
    let one_row_relations: HashSet<String> = request
        .relation_keys
        .iter()
        .filter(|(_, keys)| keys.iter().any(Vec::is_empty))
        .map(|(name, _)| name.to_ascii_lowercase())
        .collect();
    let relation_names: HashMap<String, String> = request
        .relation_names
        .iter()
        .map(|(sentinel, name)| (sentinel.to_ascii_lowercase(), name.clone()))
        .collect();
    let inputs = OneRowInputs {
        one_row_relations: &one_row_relations,
        relation_names: &relation_names,
    };
    multiplying_cross_joins(
        request.statements,
        request.tokens,
        request.cross_spans,
        &inputs,
    )
    .into_iter()
    .map(|finding| LintDiagnostic {
        code: rule.code,
        message: finding
            .relation
            .as_deref()
            .map_or(Cow::Borrowed(CROSS_JOIN_UNNAMED_MESSAGE), |relation| {
                Cow::Owned(cross_join_message(relation, finding.cte.as_deref()))
            }),
        remediation: if finding.relation.is_some() {
            Cow::Borrowed(rule.remediation)
        } else {
            Cow::Owned(file_wide_remediation(rule.code))
        },
        start: finding.span.start,
        end: finding.span.end,
        fix_unavailable_reason: Some(CROSS_JOIN_FIX_REASON),
        fix: None,
    })
    .collect()
}

/// Help for a join no relation names: fix it, or record the file-wide exception it allows.
fn file_wide_remediation(code: &str) -> String {
    let entry: String = [
        "[[rules.rule_exceptions]]".to_owned(),
        format!("rule = \"{code}\""),
        format!("path = \"{CROSS_JOIN_PATH_PLACEHOLDER}\""),
        format!("reason = \"{CROSS_JOIN_REASON_PLACEHOLDER}\""),
    ]
    .iter()
    .map(|line| format!("\n{SETTING_SNIPPET_INDENT}{line}"))
    .collect();
    format!(
        "Use a keyed JOIN, or make one side provably at most one row. This join reads no named \
         relation, so a relation-level exception cannot cover it; when the cartesian product is \
         intentional, record a reviewed file-wide exception in sqlbuild_project.toml:{entry}"
    )
}

/// The finding message naming the joined relation and, inside a CTE, that CTE.
fn cross_join_message(relation: &str, cte: Option<&str>) -> String {
    match cte {
        Some(cte) => {
            format!("{CROSS_JOIN_PREFIX}{relation}{CROSS_JOIN_CTE_MARKER}{cte}{CROSS_JOIN_SUFFIX}")
        }
        None => format!("{CROSS_JOIN_PREFIX}{relation}{CROSS_JOIN_SUFFIX}"),
    }
}

/// One explicit cross join found in the query tree.
struct CrossJoinTarget {
    /// Character offsets where the joined relation may start in the token stream.
    anchors: Vec<usize>,
    /// Whether both joined sides may hold more than one row.
    multiplies: bool,
    /// The joined relation's name as authored, with dependency sentinels resolved.
    relation: Option<String>,
    /// The top-level CTE whose query contains the join.
    cte: Option<String>,
}

/// The cross join reported at one `CROSS` keyword.
struct CrossJoinFinding {
    span: Span,
    relation: Option<String>,
    cte: Option<String>,
}

/// What the analysis knows about relations named in the query.
struct OneRowInputs<'a> {
    /// Lowercased dependency sentinels whose relation holds at most one row.
    one_row_relations: &'a HashSet<String>,
    /// Lowercased dependency sentinels mapped to the relation names they stand for.
    relation_names: &'a HashMap<String, String>,
}

struct Analysis<'a> {
    inputs: &'a OneRowInputs<'a>,
    ctes: HashMap<String, bool>,
    targets: Vec<CrossJoinTarget>,
}

/// Cross joins at `cross_spans` that can multiply rows, each with its relation and CTE.
fn multiplying_cross_joins(
    statements: &[Expression],
    tokens: &[Token],
    cross_spans: &[Span],
    inputs: &OneRowInputs<'_>,
) -> Vec<CrossJoinFinding> {
    if cross_spans.is_empty() {
        return Vec::new();
    }
    let mut analysis = Analysis {
        inputs,
        ctes: HashMap::new(),
        targets: Vec::new(),
    };
    for statement in statements {
        analysis.record_ctes(statement);
    }
    for statement in statements {
        analysis.visit(statement, None, true);
    }
    let significant: Vec<usize> = (0..tokens.len())
        .filter(|&index| {
            !matches!(
                tokens[index].token_type,
                TokenType::Space
                    | TokenType::Break
                    | TokenType::LineComment
                    | TokenType::BlockComment
            )
        })
        .collect();
    let mut findings: Vec<CrossJoinFinding> = Vec::new();
    for span in cross_spans {
        let candidates: Vec<usize> = relation_anchor_candidates(tokens, &significant, *span);
        let target: Option<&CrossJoinTarget> = analysis
            .targets
            .iter()
            .find(|target| anchored_at(target, &candidates));
        match target {
            Some(target) if !target.multiplies => {}
            Some(target) => findings.push(CrossJoinFinding {
                span: *span,
                relation: target.relation.clone(),
                cte: target.cte.clone(),
            }),
            None => findings.push(CrossJoinFinding {
                span: *span,
                relation: None,
                cte: None,
            }),
        }
    }
    findings
}

impl Analysis<'_> {
    /// Record whether every CTE holds at most one row, in definition order.
    fn record_ctes(&mut self, expression: &Expression) {
        for node in expression.dfs() {
            let Some(with) = with_clause(node) else {
                continue;
            };
            for cte in &with.ctes {
                let one_row: bool = !with.recursive && self.at_most_one_row(&cte.this);
                let name: String = cte.alias.name.to_ascii_lowercase();
                let known: bool = self.ctes.get(&name).copied().unwrap_or(one_row);
                self.ctes.insert(name, known && one_row);
            }
        }
    }

    /// Record joins under `expression`, labelled with the top-level CTE containing them.
    fn visit(&mut self, expression: &Expression, cte: Option<&str>, top: bool) {
        let mut bodies: Vec<&Expression> = Vec::new();
        if let Some(with) = with_clause(expression) {
            for definition in &with.ctes {
                bodies.push(&definition.this);
                let label: Option<&str> = if top {
                    Some(&definition.alias.name)
                } else {
                    cte
                };
                self.visit(&definition.this, label, false);
            }
        }
        if let Expression::Select(select) = expression {
            self.record_joins(select, cte);
        }
        let branches_are_top: bool = top && is_set_operation(expression);
        for child in expression.children() {
            if bodies.iter().any(|body| std::ptr::eq(*body, child)) {
                continue;
            }
            self.visit(child, cte, branches_are_top);
        }
    }

    fn record_joins(&mut self, select: &Select, cte: Option<&str>) {
        let single_from: Option<&Expression> = select
            .from
            .as_ref()
            .filter(|from| from.expressions.len() == 1)
            .and_then(|from| from.expressions.first());
        for (index, join) in select.joins.iter().enumerate() {
            if join.kind != JoinKind::Cross {
                continue;
            }
            let left_one_row: bool =
                index == 0 && single_from.is_some_and(|from| self.relation_one_row(from));
            let multiplies: bool = !(left_one_row || self.relation_one_row(&join.this));
            self.targets.push(CrossJoinTarget {
                anchors: relation_anchors(&join.this),
                multiplies,
                relation: self.relation_name(&join.this),
                cte: cte.map(str::to_owned),
            });
        }
    }

    fn relation_name(&self, relation: &Expression) -> Option<String> {
        match relation {
            Expression::Table(table) => Some(self.table_name(table)),
            Expression::Subquery(subquery) => {
                subquery.alias.as_ref().map(|alias| alias.name.clone())
            }
            Expression::Alias(alias) => Some(alias.alias.name.clone()),
            _ => None,
        }
    }

    fn table_name(&self, table: &TableRef) -> String {
        if table.schema.is_none() && table.catalog.is_none() {
            let lowered: String = table.name.name.to_ascii_lowercase();
            if let Some(name) = self.inputs.relation_names.get(&lowered) {
                return name.clone();
            }
        }
        [&table.catalog, &table.schema]
            .into_iter()
            .flatten()
            .map(|part| part.name.as_str())
            .chain([table.name.name.as_str()])
            .collect::<Vec<&str>>()
            .join(".")
    }

    /// Whether a query expression returns at most one row.
    fn at_most_one_row(&self, expression: &Expression) -> bool {
        match expression {
            Expression::Select(select) => self.select_one_row(select),
            Expression::Subquery(subquery) => self.subquery_one_row(subquery),
            Expression::Paren(paren) => self.at_most_one_row(&paren.this),
            Expression::Values(values) => values.expressions.len() <= 1,
            _ => false,
        }
    }

    fn subquery_one_row(&self, subquery: &Subquery) -> bool {
        !subquery.lateral
            && (subquery
                .limit
                .as_ref()
                .is_some_and(|limit| !limit.percent && at_most_one(&limit.this))
                || self.at_most_one_row(&subquery.this))
    }

    fn select_one_row(&self, select: &Select) -> bool {
        if select.limit_by.is_some() || select.connect.is_some() || !select.lateral_views.is_empty()
        {
            return false;
        }
        if limited_to_one_row(select) {
            return true;
        }
        if select.expressions.iter().any(generates_rows) {
            return false;
        }
        if select.group_by.is_none() && select.expressions.iter().any(aggregates) {
            return true;
        }
        if select
            .qualify
            .as_ref()
            .is_some_and(|qualify| first_unpartitioned_row(&qualify.this, select))
        {
            return true;
        }
        if select.group_by.is_some() || !select.joins.is_empty() {
            return false;
        }
        match &select.from {
            None => true,
            Some(from) => match from.expressions.as_slice() {
                [relation] => self.relation_one_row(relation),
                _ => false,
            },
        }
    }

    /// Whether a relation in FROM or JOIN holds at most one row.
    fn relation_one_row(&self, relation: &Expression) -> bool {
        match relation {
            Expression::Table(table) => {
                if table.schema.is_some()
                    || table.catalog.is_some()
                    || table.identifier_func.is_some()
                    || table.changes.is_some()
                {
                    return false;
                }
                let name: String = table.name.name.to_ascii_lowercase();
                match self.ctes.get(&name) {
                    Some(one_row) => *one_row,
                    None => self.inputs.one_row_relations.contains(&name),
                }
            }
            Expression::Subquery(subquery) => self.subquery_one_row(subquery),
            Expression::Paren(paren) => self.relation_one_row(&paren.this),
            Expression::Values(values) => values.expressions.len() <= 1,
            _ => false,
        }
    }
}

/// The WITH clause a query expression owns.
fn with_clause(expression: &Expression) -> Option<&With> {
    match expression {
        Expression::Select(select) => select.with.as_ref(),
        Expression::Union(union) => union.with.as_ref(),
        Expression::Intersect(intersect) => intersect.with.as_ref(),
        Expression::Except(except) => except.with.as_ref(),
        _ => None,
    }
}

fn is_set_operation(expression: &Expression) -> bool {
    matches!(
        expression,
        Expression::Union(_) | Expression::Intersect(_) | Expression::Except(_)
    )
}

fn limited_to_one_row(select: &Select) -> bool {
    let limited: bool = select
        .limit
        .as_ref()
        .is_some_and(|limit| !limit.percent && at_most_one(&limit.this));
    let fetched: bool = select.fetch.as_ref().is_some_and(|fetch| {
        !fetch.percent && !fetch.with_ties && fetch.count.as_ref().is_some_and(at_most_one)
    });
    let top: bool = select
        .top
        .as_ref()
        .is_some_and(|top| !top.percent && !top.with_ties && at_most_one(&top.this));
    limited || fetched || top
}

fn at_most_one(expression: &Expression) -> bool {
    match expression {
        Expression::Literal(literal) => match literal.as_ref() {
            Literal::Number(text) => text.parse::<u64>().is_ok_and(|count| count <= 1),
            _ => false,
        },
        Expression::Paren(paren) => at_most_one(&paren.this),
        _ => false,
    }
}

/// Whether a projected expression can return several rows per input row.
fn generates_rows(expression: &Expression) -> bool {
    expression.dfs().any(|node| match node {
        Expression::Unnest(_)
        | Expression::Explode(_)
        | Expression::ExplodeOuter(_)
        | Expression::GenerateSeries(_) => true,
        Expression::Function(function) => is_row_generator(&function.name),
        _ => false,
    })
}

fn is_row_generator(name: &str) -> bool {
    let name: &str = name.rsplit('.').next().unwrap_or_default();
    ROW_GENERATOR_FUNCTIONS
        .iter()
        .any(|generator| generator.eq_ignore_ascii_case(name))
}

fn anchored_at(target: &CrossJoinTarget, candidates: &[usize]) -> bool {
    target
        .anchors
        .iter()
        .any(|anchor| candidates.contains(anchor))
}

/// Whether an expression aggregates outside any window function or subquery.
fn aggregates(expression: &Expression) -> bool {
    if polyglot_sql::traversal::is_aggregate(expression) {
        return true;
    }
    match expression {
        Expression::WindowFunction(_) | Expression::Subquery(_) | Expression::Select(_) => false,
        _ => expression.children().into_iter().any(aggregates),
    }
}

/// `QUALIFY ROW_NUMBER() OVER (ORDER BY ...) = 1` without a partition, directly or by alias.
fn first_unpartitioned_row(condition: &Expression, select: &Select) -> bool {
    match condition {
        Expression::And(operation) => {
            first_unpartitioned_row(&operation.left, select)
                || first_unpartitioned_row(&operation.right, select)
        }
        Expression::Paren(paren) => first_unpartitioned_row(&paren.this, select),
        Expression::Eq(operation) => {
            let compared: &Expression = match (&operation.left, &operation.right) {
                (other, Expression::Literal(literal)) | (Expression::Literal(literal), other)
                    if matches!(literal.as_ref(), Literal::Number(text) if text == FIRST_ROW) =>
                {
                    other
                }
                _ => return false,
            };
            match compared {
                Expression::WindowFunction(_) => unpartitioned_row_number(compared),
                Expression::Column(column) if column.table.is_none() => select
                    .expressions
                    .iter()
                    .any(|projection| match projection {
                        Expression::Alias(alias) => {
                            alias.alias.name.eq_ignore_ascii_case(&column.name.name)
                                && unpartitioned_row_number(&alias.this)
                        }
                        _ => false,
                    }),
                _ => false,
            }
        }
        _ => false,
    }
}

fn unpartitioned_row_number(expression: &Expression) -> bool {
    matches!(
        expression,
        Expression::WindowFunction(window)
            if matches!(window.this, Expression::RowNumber(_))
                && window.over.window_name.is_none()
                && window.over.partition_by.is_empty()
    )
}

/// Where a joined relation can start: its first name part, or a derived table's alias.
fn relation_anchors(relation: &Expression) -> Vec<usize> {
    match relation {
        Expression::Table(table) => {
            let mut anchors: Vec<usize> = Vec::new();
            for identifier in [&table.catalog, &table.schema].into_iter().flatten() {
                anchors.extend(identifier.span.map(|span| span.start));
            }
            anchors.extend(table.name.span.map(|span| span.start));
            anchors.extend(table.span.map(|span| span.start));
            anchors
        }
        Expression::Subquery(subquery) => subquery
            .alias
            .as_ref()
            .and_then(|alias| alias.span)
            .map(|span| span.start)
            .into_iter()
            .collect(),
        Expression::Alias(alias) => alias
            .alias
            .span
            .map(|span| span.start)
            .into_iter()
            .collect(),
        _ => Vec::new(),
    }
}

/// Where the relation after `CROSS JOIN` at `cross` starts, and a derived table's alias.
fn relation_anchor_candidates(tokens: &[Token], significant: &[usize], cross: Span) -> Vec<usize> {
    let Some(position) = significant
        .iter()
        .position(|&index| tokens[index].span.start == cross.start)
    else {
        return Vec::new();
    };
    let Some(&first) = significant.get(position + 2) else {
        return Vec::new();
    };
    let mut candidates: Vec<usize> = vec![tokens[first].span.start];
    if tokens[first].token_type == TokenType::LParen {
        let mut depth: usize = 0;
        let mut cursor: usize = position + 2;
        while let Some(&index) = significant.get(cursor) {
            match tokens[index].token_type {
                TokenType::LParen => depth += 1,
                TokenType::RParen => {
                    depth = depth.saturating_sub(1);
                    if depth == 0 {
                        break;
                    }
                }
                _ => {}
            }
            cursor += 1;
        }
        let mut alias: usize = cursor + 1;
        if significant
            .get(alias)
            .is_some_and(|&index| tokens[index].token_type == TokenType::As)
        {
            alias += 1;
        }
        if let Some(&index) = significant.get(alias) {
            candidates.push(tokens[index].span.start);
        }
    }
    candidates
}
