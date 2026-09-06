use std::collections::{HashMap, HashSet, VecDeque};
use std::str::FromStr;

use polyglot_sql::expressions::With;
use polyglot_sql::parser::ParserConfig;
use polyglot_sql::tokens::{Span, Token, TokenType};
use polyglot_sql::{Dialect, DialectType, Expression, ExpressionWalk, Parser};

use crate::sql_lint::constants::LINT_API_VERSION;
use crate::sql_lint::models::{
    LintDiagnostic, LintRequest, LintResponse, LintRuleMetadata, QueryFacts,
};

const NULL_COMPARISON: LintRuleMetadata = LintRuleMetadata {
    code: "SQBL001",
    message: "Comparison with NULL is never true",
    remediation: "Use IS NULL or IS NOT NULL when testing for NULL.",
};
const IMPLICIT_CARTESIAN_JOIN: LintRuleMetadata = LintRuleMetadata {
    code: "SQBL002",
    message: "Comma-separated sources create an implicit cartesian join",
    remediation: "Replace comma-separated sources with an explicit keyed join, or use CROSS JOIN when the cartesian product is intentional.",
};
const JOIN_WITHOUT_CONDITION: LintRuleMetadata = LintRuleMetadata {
    code: "SQBL003",
    message: "Non-cross join has no meaningful condition",
    remediation: "Add a meaningful ON or USING condition, or declare an intentional cartesian product with CROSS JOIN.",
};
const UNORDERED_LIMIT: LintRuleMetadata = LintRuleMetadata {
    code: "SQBL004",
    message: "Row selection is nondeterministic",
    remediation: "Add ORDER BY with a deterministic tie-breaker before LIMIT or OFFSET.",
};
const UNUSED_CTE: LintRuleMetadata = LintRuleMetadata {
    code: "SQBL005",
    message: "CTE is unreachable from the final query",
    remediation: "Reference the CTE from the final query or another reachable CTE, or remove it.",
};
const REDUNDANT_DISTINCT: LintRuleMetadata = LintRuleMetadata {
    code: "SQBL006",
    message: "DISTINCT is redundant with the grouped output",
    remediation: "Remove DISTINCT; the equivalent GROUP BY already determines the output groups.",
};
const POSITIONAL_SET_STAR: LintRuleMetadata = LintRuleMetadata {
    code: "SQBL007",
    message: "Positional set operation is vulnerable to column-order drift",
    remediation: "Enumerate columns in the same order in every set-operation branch.",
};
const TRIVIAL_EQUALITY_TOKEN_COUNT: usize = 3;

const DEFAULT_RULES: [&str; 7] = [
    NULL_COMPARISON.code,
    IMPLICIT_CARTESIAN_JOIN.code,
    JOIN_WITHOUT_CONDITION.code,
    UNORDERED_LIMIT.code,
    UNUSED_CTE.code,
    REDUNDANT_DISTINCT.code,
    POSITIONAL_SET_STAR.code,
];

struct QueryTokenContext<'a> {
    tokens: &'a [Token],
    depths: &'a [usize],
    direct: &'a [usize],
    query_end: usize,
    depth: usize,
}

struct ExpressionRange {
    start: usize,
    end: usize,
    depth: usize,
    strip_alias: bool,
}

pub(crate) fn lint_json_impl(request_json: &str) -> Result<String, String> {
    let request: LintRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let response = lint(request)?;
    serde_json::to_string(&response).map_err(|error| error.to_string())
}

fn lint(request: LintRequest) -> Result<LintResponse, String> {
    if request.version != LINT_API_VERSION {
        return Err(format!(
            "unsupported native lint request version {}; expected {LINT_API_VERSION}",
            request.version
        ));
    }
    let enabled = enabled_rules(request.enabled_rules)?;
    let dialect_type =
        DialectType::from_str(&request.dialect).map_err(|error| error.to_string())?;
    let dialect = Dialect::get(dialect_type);
    let tokens = dialect
        .tokenize(&request.sql)
        .map_err(|error| error.to_string())?;
    let mut parser = Parser::with_config(
        tokens.clone(),
        ParserConfig {
            dialect: Some(dialect_type),
            ..Default::default()
        },
    );
    let statements = parser.parse().map_err(|error| error.to_string())?;
    let facts = build_facts(&statements, &tokens);
    let mut diagnostics = diagnostics(&facts, &tokens, &enabled);
    diagnostics.sort_by_key(|diagnostic| (diagnostic.start, diagnostic.end, diagnostic.code));
    Ok(LintResponse {
        version: LINT_API_VERSION,
        diagnostics,
    })
}

fn enabled_rules(requested: Option<Vec<String>>) -> Result<HashSet<String>, String> {
    let rules =
        requested.unwrap_or_else(|| DEFAULT_RULES.iter().map(ToString::to_string).collect());
    let known: HashSet<&str> = DEFAULT_RULES.into_iter().collect();
    if let Some(unknown) = rules.iter().find(|rule| !known.contains(rule.as_str())) {
        return Err(format!("unknown native lint rule '{unknown}'"));
    }
    Ok(rules.into_iter().collect())
}

fn build_facts(expressions: &[Expression], tokens: &[Token]) -> QueryFacts {
    let mut facts: QueryFacts = collect_token_query_facts(tokens);
    facts.null_comparisons = null_comparison_spans(tokens);
    for expression in expressions {
        facts
            .unused_cte_names
            .extend(collect_unused_ctes(expression));
    }
    facts
}

fn collect_token_query_facts(tokens: &[Token]) -> QueryFacts {
    let mut facts = QueryFacts::default();
    let depths = token_depths(tokens);
    for (select_index, token) in tokens.iter().enumerate() {
        if token.token_type != TokenType::Select {
            continue;
        }
        let depth = depths[select_index];
        let end = query_end(tokens, &depths, select_index, depth);
        let direct = direct_indices(&depths, select_index + 1, end, depth);
        let order = first_type(tokens, &direct, TokenType::Order);
        let limit = first_type(tokens, &direct, TokenType::Limit)
            .or_else(|| first_type(tokens, &direct, TokenType::Offset));
        if order.is_none()
            && let Some(index) = limit
        {
            facts.unordered_limits.push(tokens[index].span);
        }
        let context = QueryTokenContext {
            tokens,
            depths: &depths,
            direct: &direct,
            query_end: end,
            depth,
        };
        if let Some(span) = redundant_distinct_span(&context) {
            facts.redundant_distincts.push(span);
        }
        let (implicit, missing_conditions) = collect_from_and_join_facts(tokens, &direct);
        facts.implicit_cartesian_joins.extend(implicit);
        facts.joins_without_condition.extend(missing_conditions);
    }
    facts.positional_set_stars = collect_set_operation_facts(tokens, &depths);
    facts
}

fn token_depths(tokens: &[Token]) -> Vec<usize> {
    let mut depth = 0_usize;
    tokens
        .iter()
        .map(|token| {
            let current = depth;
            if token.token_type == TokenType::LParen {
                depth += 1;
            } else if token.token_type == TokenType::RParen {
                depth = depth.saturating_sub(1);
            }
            current
        })
        .collect()
}

fn query_end(tokens: &[Token], depths: &[usize], start: usize, depth: usize) -> usize {
    (start + 1..tokens.len())
        .find(|&index| {
            depths[index] < depth
                || depths[index] == depth
                    && matches!(
                        tokens[index].token_type,
                        TokenType::RParen
                            | TokenType::Semicolon
                            | TokenType::Union
                            | TokenType::Intersect
                            | TokenType::Except
                    )
        })
        .unwrap_or(tokens.len())
}

fn direct_indices(depths: &[usize], start: usize, end: usize, depth: usize) -> Vec<usize> {
    (start..end)
        .filter(|&index| depths[index] == depth)
        .collect()
}

fn first_type(tokens: &[Token], indices: &[usize], token_type: TokenType) -> Option<usize> {
    indices
        .iter()
        .copied()
        .find(|&index| tokens[index].token_type == token_type)
}

fn redundant_distinct_span(context: &QueryTokenContext<'_>) -> Option<Span> {
    let QueryTokenContext {
        tokens,
        depths,
        direct,
        query_end,
        depth,
    } = context;
    let distinct_position = direct
        .iter()
        .position(|&index| tokens[index].token_type == TokenType::Distinct)?;
    if direct
        .get(distinct_position + 1)
        .is_some_and(|&index| tokens[index].token_type == TokenType::On)
    {
        return None;
    }
    let group_position = group_by_position(tokens, direct)?;
    let group_index = direct[group_position];
    let projection_end = first_type(tokens, direct, TokenType::From)
        .filter(|index| *index < group_index)
        .unwrap_or(group_index);
    let projection_start = direct[distinct_position] + 1;
    let group_start = *direct.get(group_position + 2)?;
    let group_end = direct[group_position + 2..]
        .iter()
        .copied()
        .find(|&index| {
            matches!(
                tokens[index].token_type,
                TokenType::Having
                    | TokenType::Qualify
                    | TokenType::Order
                    | TokenType::Limit
                    | TokenType::Offset
            )
        })
        .unwrap_or(*query_end);
    let projection_signatures = expression_signatures(
        tokens,
        depths,
        &ExpressionRange {
            start: projection_start,
            end: projection_end,
            depth: *depth,
            strip_alias: true,
        },
    );
    let group_signatures = expression_signatures(
        tokens,
        depths,
        &ExpressionRange {
            start: group_start,
            end: group_end,
            depth: *depth,
            strip_alias: false,
        },
    );
    if group_signatures.is_empty()
        || !group_signatures
            .iter()
            .all(|group| projection_signatures.contains(group))
    {
        return None;
    }
    Some(tokens[direct[distinct_position]].span)
}

fn group_by_position(tokens: &[Token], direct: &[usize]) -> Option<usize> {
    direct.windows(2).position(|window| {
        tokens[window[0]].token_type == TokenType::Group
            && tokens[window[1]].text.eq_ignore_ascii_case("BY")
    })
}

fn expression_signatures(
    tokens: &[Token],
    depths: &[usize],
    range: &ExpressionRange,
) -> Vec<String> {
    let mut boundaries: Vec<usize> = (range.start..range.end)
        .filter(|&index| {
            depths[index] == range.depth && tokens[index].token_type == TokenType::Comma
        })
        .collect();
    boundaries.push(range.end);
    let mut segment_start = range.start;
    let mut signatures: Vec<String> = Vec::new();
    for segment_end in boundaries {
        let effective_end = alias_start(tokens, depths, range, segment_start..segment_end);
        let parts: Vec<String> = tokens[segment_start..effective_end]
            .iter()
            .map(|token| token.text.to_ascii_lowercase())
            .collect();
        let signature = parts.join(" ");
        if !signature.is_empty() {
            signatures.push(signature);
        }
        segment_start = segment_end + 1;
    }
    signatures
}

fn alias_start(
    tokens: &[Token],
    depths: &[usize],
    range: &ExpressionRange,
    segment: std::ops::Range<usize>,
) -> usize {
    if !range.strip_alias {
        return segment.end;
    }
    segment
        .clone()
        .find(|&index| depths[index] == range.depth && tokens[index].token_type == TokenType::As)
        .unwrap_or(segment.end)
}

fn collect_from_and_join_facts(tokens: &[Token], direct: &[usize]) -> (Vec<Span>, Vec<Span>) {
    let mut implicit: Vec<Span> = Vec::new();
    let mut missing_conditions: Vec<Span> = Vec::new();
    let Some(from_position) = direct
        .iter()
        .position(|&index| tokens[index].token_type == TokenType::From)
    else {
        return (implicit, missing_conditions);
    };
    let clause_end = direct[from_position + 1..]
        .iter()
        .position(|&index| is_post_from_clause(tokens[index].token_type))
        .map_or(direct.len(), |offset| from_position + 1 + offset);
    for &index in &direct[from_position + 1..clause_end] {
        if tokens[index].token_type == TokenType::Comma {
            implicit.push(tokens[index].span);
        }
    }
    for (position, &index) in direct.iter().enumerate() {
        if tokens[index].token_type != TokenType::Join
            || is_conditionless_join(tokens, direct, position)
        {
            continue;
        }
        let condition_end = direct[position + 1..]
            .iter()
            .position(|&candidate| {
                tokens[candidate].token_type == TokenType::Join
                    || is_post_from_clause(tokens[candidate].token_type)
            })
            .map_or(direct.len(), |offset| position + 1 + offset);
        let condition = &direct[position + 1..condition_end];
        let on_position = condition
            .iter()
            .position(|&candidate| tokens[candidate].token_type == TokenType::On);
        let has_using = condition
            .iter()
            .any(|&candidate| tokens[candidate].token_type == TokenType::Using);
        if !has_using
            && on_position
                .is_none_or(|offset| trivial_on_condition(tokens, &condition[offset + 1..]))
        {
            missing_conditions.push(tokens[index].span);
        }
    }
    (implicit, missing_conditions)
}

fn is_post_from_clause(token_type: TokenType) -> bool {
    matches!(
        token_type,
        TokenType::Join
            | TokenType::Where
            | TokenType::Group
            | TokenType::Having
            | TokenType::Qualify
            | TokenType::Order
            | TokenType::Limit
            | TokenType::Offset
            | TokenType::Fetch
    )
}

fn is_conditionless_join(tokens: &[Token], direct: &[usize], join_position: usize) -> bool {
    direct[..join_position]
        .iter()
        .rev()
        .take_while(|&&index| {
            !matches!(
                tokens[index].token_type,
                TokenType::From | TokenType::Join | TokenType::Comma
            )
        })
        .any(|&index| {
            matches!(
                tokens[index].text.to_ascii_uppercase().as_str(),
                "CROSS" | "NATURAL" | "APPLY" | "POSITIONAL" | "PASTE"
            )
        })
}

fn trivial_on_condition(tokens: &[Token], condition: &[usize]) -> bool {
    let significant: Vec<&Token> = condition
        .iter()
        .map(|&index| &tokens[index])
        .filter(|token| !matches!(token.token_type, TokenType::LParen | TokenType::RParen))
        .collect();
    significant.is_empty()
        || significant.len() == 1 && significant[0].token_type == TokenType::True
        || significant.len() == TRIVIAL_EQUALITY_TOKEN_COUNT
            && significant[1].token_type == TokenType::Eq
            && matches!(
                significant[0].token_type,
                TokenType::Number | TokenType::String | TokenType::True | TokenType::False
            )
            && significant[0].token_type == significant[2].token_type
            && significant[0].text == significant[2].text
}

fn collect_set_operation_facts(tokens: &[Token], depths: &[usize]) -> Vec<Span> {
    let mut spans: Vec<Span> = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        if !matches!(
            token.token_type,
            TokenType::Union | TokenType::Intersect | TokenType::Except
        ) {
            continue;
        }
        let depth = depths[index];
        let by_name = tokens[index + 1..]
            .iter()
            .take_while(|candidate| candidate.token_type != TokenType::Select)
            .any(|candidate| candidate.text.eq_ignore_ascii_case("BY"))
            && tokens[index + 1..]
                .iter()
                .take_while(|candidate| candidate.token_type != TokenType::Select)
                .any(|candidate| candidate.text.eq_ignore_ascii_case("NAME"));
        if !by_name
            && (select_before_projects_star(tokens, depths, index, depth)
                || select_after_projects_star(tokens, depths, index, depth))
        {
            spans.push(token.span);
        }
    }
    spans
}

fn select_before_projects_star(
    tokens: &[Token],
    depths: &[usize],
    end: usize,
    depth: usize,
) -> bool {
    let Some(start) = (0..end)
        .rev()
        .find(|&index| depths[index] == depth && tokens[index].token_type == TokenType::Select)
        .or_else(|| {
            (0..end)
                .rev()
                .filter(|&index| tokens[index].token_type == TokenType::Select)
                .min_by_key(|&index| depths[index])
        })
    else {
        return false;
    };
    projection_projects_star(
        tokens,
        depths,
        &ExpressionRange {
            start,
            end,
            depth: depths[start],
            strip_alias: false,
        },
    )
}

fn select_after_projects_star(
    tokens: &[Token],
    depths: &[usize],
    start: usize,
    depth: usize,
) -> bool {
    let Some(select) = (start + 1..tokens.len())
        .find(|&index| depths[index] == depth && tokens[index].token_type == TokenType::Select)
        .or_else(|| {
            (start + 1..tokens.len())
                .filter(|&index| tokens[index].token_type == TokenType::Select)
                .min_by_key(|&index| depths[index])
        })
    else {
        return false;
    };
    let select_depth = depths[select];
    projection_projects_star(
        tokens,
        depths,
        &ExpressionRange {
            start: select,
            end: query_end(tokens, depths, select, select_depth),
            depth: select_depth,
            strip_alias: false,
        },
    )
}

fn projection_projects_star(tokens: &[Token], depths: &[usize], range: &ExpressionRange) -> bool {
    (range.start + 1..range.end)
        .take_while(|&index| {
            depths[index] != range.depth || tokens[index].token_type != TokenType::From
        })
        .any(|index| depths[index] == range.depth && tokens[index].token_type == TokenType::Star)
}

fn collect_unused_ctes(expression: &Expression) -> Vec<String> {
    let mut unused: Vec<String> = Vec::new();
    for node in expression.dfs() {
        match node {
            Expression::Select(select) if select.with.is_some() => {
                let mut root = select.clone();
                if let Some(with) = root.with.take() {
                    unused.extend(collect_unused_for_with(&with, &Expression::Select(root)));
                }
            }
            Expression::Union(operation) if operation.with.is_some() => {
                let mut root = operation.clone();
                if let Some(with) = root.with.take() {
                    unused.extend(collect_unused_for_with(&with, &Expression::Union(root)));
                }
            }
            Expression::Intersect(operation) if operation.with.is_some() => {
                let mut root = operation.clone();
                if let Some(with) = root.with.take() {
                    unused.extend(collect_unused_for_with(&with, &Expression::Intersect(root)));
                }
            }
            Expression::Except(operation) if operation.with.is_some() => {
                let mut root = operation.clone();
                if let Some(with) = root.with.take() {
                    unused.extend(collect_unused_for_with(&with, &Expression::Except(root)));
                }
            }
            _ => {}
        };
    }
    unused
}

fn collect_unused_for_with(with: &With, root: &Expression) -> Vec<String> {
    let names: HashSet<String> = with
        .ctes
        .iter()
        .map(|cte| cte.alias.name.to_ascii_lowercase())
        .collect();
    let dependencies: HashMap<String, HashSet<String>> = with
        .ctes
        .iter()
        .map(|cte| {
            (
                cte.alias.name.to_ascii_lowercase(),
                table_names(&cte.this)
                    .intersection(&names)
                    .cloned()
                    .collect(),
            )
        })
        .collect();
    let mut reachable: HashSet<String> = table_names(root).intersection(&names).cloned().collect();
    let mut queue: VecDeque<String> = reachable.iter().cloned().collect();
    while let Some(name) = queue.pop_front() {
        if let Some(required) = dependencies.get(&name) {
            for dependency in required {
                if reachable.insert(dependency.clone()) {
                    queue.push_back(dependency.clone());
                }
            }
        }
    }
    with.ctes
        .iter()
        .filter(|cte| !reachable.contains(&cte.alias.name.to_ascii_lowercase()))
        .map(|cte| cte.alias.name.clone())
        .collect()
}

fn table_names(expression: &Expression) -> HashSet<String> {
    expression
        .dfs()
        .filter_map(|node| match node {
            Expression::Table(table) => Some(table.name.name.to_ascii_lowercase()),
            _ => None,
        })
        .collect()
}

fn diagnostics(
    facts: &QueryFacts,
    tokens: &[Token],
    enabled: &HashSet<String>,
) -> Vec<LintDiagnostic> {
    let mut diagnostics: Vec<LintDiagnostic> = Vec::new();
    if enabled.contains(NULL_COMPARISON.code) {
        diagnostics.extend(diagnostics_for_spans(
            &NULL_COMPARISON,
            &facts.null_comparisons,
        ));
    }
    if enabled.contains(IMPLICIT_CARTESIAN_JOIN.code) {
        diagnostics.extend(diagnostics_for_spans(
            &IMPLICIT_CARTESIAN_JOIN,
            &facts.implicit_cartesian_joins,
        ));
    }
    if enabled.contains(JOIN_WITHOUT_CONDITION.code) {
        diagnostics.extend(diagnostics_for_spans(
            &JOIN_WITHOUT_CONDITION,
            &facts.joins_without_condition,
        ));
    }
    if enabled.contains(UNORDERED_LIMIT.code) {
        diagnostics.extend(diagnostics_for_spans(
            &UNORDERED_LIMIT,
            &facts.unordered_limits,
        ));
    }
    if enabled.contains(UNUSED_CTE.code) {
        for span in unused_cte_spans(tokens, &facts.unused_cte_names) {
            diagnostics.push(diagnostic(&UNUSED_CTE, Some(span)));
        }
    }
    if enabled.contains(REDUNDANT_DISTINCT.code) {
        diagnostics.extend(diagnostics_for_spans(
            &REDUNDANT_DISTINCT,
            &facts.redundant_distincts,
        ));
    }
    if enabled.contains(POSITIONAL_SET_STAR.code) {
        diagnostics.extend(diagnostics_for_spans(
            &POSITIONAL_SET_STAR,
            &facts.positional_set_stars,
        ));
    }
    diagnostics
}

fn diagnostics_for_spans(rule: &LintRuleMetadata, spans: &[Span]) -> Vec<LintDiagnostic> {
    spans
        .iter()
        .map(|span| diagnostic(rule, Some(*span)))
        .collect()
}

fn diagnostic(rule: &LintRuleMetadata, span: Option<Span>) -> LintDiagnostic {
    let span = span.unwrap_or_default();
    LintDiagnostic {
        code: rule.code,
        message: rule.message,
        remediation: rule.remediation,
        start: span.start,
        end: span.end,
    }
}

fn unused_cte_spans(tokens: &[Token], unused_names: &[String]) -> Vec<Span> {
    let mut remaining: Vec<String> = unused_names
        .iter()
        .map(|name| name.to_ascii_lowercase())
        .collect();
    let mut spans: Vec<Span> = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        let name = token.text.to_ascii_lowercase();
        let Some(position) = remaining.iter().position(|candidate| candidate == &name) else {
            continue;
        };
        if tokens
            .get(index + 1)
            .is_some_and(|next| next.token_type == TokenType::As)
        {
            remaining.remove(position);
            spans.push(token.span);
        }
    }
    spans
}

fn null_comparison_spans(tokens: &[Token]) -> Vec<Span> {
    let comparison_types = [
        TokenType::Eq,
        TokenType::Neq,
        TokenType::Lt,
        TokenType::Lte,
        TokenType::Gt,
        TokenType::Gte,
    ];
    let depths = token_depths(tokens);
    tokens
        .iter()
        .enumerate()
        .filter(|(_, token)| comparison_types.contains(&token.token_type))
        .filter(|(index, _)| !is_assignment_operator(tokens, &depths, *index))
        .filter(|(index, _)| {
            adjacent_null(tokens, *index, false) || adjacent_null(tokens, *index, true)
        })
        .map(|(_, token)| token.span)
        .collect()
}

fn is_assignment_operator(tokens: &[Token], depths: &[usize], operator_index: usize) -> bool {
    let depth = depths[operator_index];
    for index in (0..operator_index).rev() {
        if depths[index] != depth {
            continue;
        }
        match tokens[index].token_type {
            TokenType::Where | TokenType::Having | TokenType::Qualify | TokenType::On => {
                return false;
            }
            TokenType::Set => return true,
            TokenType::Select | TokenType::Semicolon => return false,
            _ => {}
        }
    }
    false
}

fn adjacent_null(tokens: &[Token], operator_index: usize, forward: bool) -> bool {
    let mut index = operator_index as isize + if forward { 1 } else { -1 };
    let mut wrappers = 0_usize;
    loop {
        if index < 0 {
            return false;
        }
        let Some(token) = tokens.get(index as usize) else {
            return false;
        };
        if token.token_type == TokenType::Null {
            break;
        }
        let wrapper = if forward {
            TokenType::LParen
        } else {
            TokenType::RParen
        };
        if token.token_type != wrapper {
            return false;
        }
        wrappers += 1;
        index += if forward { 1 } else { -1 };
    }
    index += if forward { 1 } else { -1 };
    let closing_wrapper = if forward {
        TokenType::RParen
    } else {
        TokenType::LParen
    };
    for _ in 0..wrappers {
        if index < 0 {
            return false;
        }
        let Some(token) = tokens.get(index as usize) else {
            return false;
        };
        if token.token_type != closing_wrapper {
            return false;
        }
        index += if forward { 1 } else { -1 };
    }
    true
}
