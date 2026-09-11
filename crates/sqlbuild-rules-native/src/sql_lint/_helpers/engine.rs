use std::collections::{HashMap, HashSet, VecDeque};
use std::str::FromStr;

use polyglot_sql::expressions::With;
use polyglot_sql::parser::ParserConfig;
use polyglot_sql::tokens::{Span, Token, TokenType};
use polyglot_sql::{
    ComplexityGuardOptions, Dialect, DialectType, Expression, ExpressionWalk, Parser,
};

use crate::sql_lint::constants::LINT_API_VERSION;
use crate::sql_lint::models::{
    LintDiagnostic, LintEdit, LintRequest, LintResponse, LintRuleMetadata, QueryFacts,
};

use crate::sql_lint::_helpers::additional::collect_additional_facts;

const NULL_COMPARISON: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL001",
    message: "Comparison with NULL is never true",
    remediation: "Use IS NULL or IS NOT NULL when testing for NULL.",
};
const MAX_LINT_FUNCTION_CALL_DEPTH: usize = 128;
const IMPLICIT_CARTESIAN_JOIN: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL002",
    message: "Comma-separated sources create an implicit cartesian join",
    remediation: "Replace comma-separated sources with an explicit keyed join, or use CROSS JOIN when the cartesian product is intentional.",
};
const JOIN_WITHOUT_CONDITION: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL003",
    message: "Non-cross join has no meaningful condition",
    remediation: "Add a meaningful ON or USING condition, or declare an intentional cartesian product with CROSS JOIN.",
};
const UNORDERED_LIMIT: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL004",
    message: "Row selection is nondeterministic",
    remediation: "Add ORDER BY with a deterministic tie-breaker before LIMIT or OFFSET.",
};
const UNUSED_CTE: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL005",
    message: "CTE is unreachable from the final query",
    remediation: "Reference the CTE from the final query or another reachable CTE, or remove it.",
};
const REDUNDANT_DISTINCT: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL006",
    message: "DISTINCT is redundant with the grouped output",
    remediation: "Remove DISTINCT; the equivalent GROUP BY already determines the output groups.",
};
const POSITIONAL_SET_STAR: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL007",
    message: "Positional set operation is vulnerable to column-order drift",
    remediation: "Enumerate columns in the same order in every set-operation branch.",
};
const EXPLICIT_UNION: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL008",
    message: "Bare UNION leaves duplicate handling implicit",
    remediation: "Use UNION DISTINCT or UNION ALL to state duplicate handling explicitly.",
};
const DUPLICATE_TABLE_ALIAS: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL009",
    message: "Table alias is duplicated in the same query scope",
    remediation: "Give every relation in this query scope a unique alias.",
};
const DUPLICATE_OUTPUT_ALIAS: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL010",
    message: "Output alias is duplicated in the same select list",
    remediation: "Give every projected expression a unique output alias.",
};
const MIXED_GROUP_ORDER_REFERENCES: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL011",
    message: "Clause mixes positional and named references",
    remediation: "Use column names or positions consistently throughout this clause.",
};
const REDUNDANT_ELSE_NULL: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL012",
    message: "ELSE NULL is redundant",
    remediation: "Remove ELSE NULL; CASE expressions return NULL when ELSE is omitted.",
};
const PARENTHESIZED_DISTINCT: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL013",
    message: "DISTINCT is written as though it were a function",
    remediation: "Write DISTINCT as a SELECT modifier without function-like parentheses.",
};
const CONSTANT_PREDICATE: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL014",
    message: "Predicate compares identical constant values",
    remediation: "Remove the scaffold predicate or replace it with the intended condition.",
};
const CONSECUTIVE_SEMICOLON: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL015",
    message: "Empty statement follows another terminator",
    remediation: "Remove the redundant statement terminator.",
};
const REDUNDANT_SELF_ALIAS: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL016",
    message: "Expression is aliased to its existing name",
    remediation: "Remove the redundant self-alias.",
};
const COUNT_ONE: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL017",
    message: "Row count uses a constant expression",
    remediation: "Use COUNT(*) to state that rows, rather than a nullable expression, are counted.",
};
const UNSTABLE_ROW_NUMBER: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL018",
    message: "ROW_NUMBER has no deterministic ordering",
    remediation: "Add ORDER BY with a stable tie-breaker inside the window specification.",
};
const NULL_NOT_IN: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL019",
    message: "NOT IN list contains NULL and can reject every row",
    remediation: "Remove NULL from the list or express the anti-join with a NULL-safe NOT EXISTS.",
};
const SET_ARITY_MISMATCH: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL020",
    message: "Set-operation branches project different column counts",
    remediation: "Project the same number of columns in every set-operation branch.",
};
const PROJECTED_STAR: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL021",
    message: "Query output has an uncontrolled column shape",
    remediation: "Enumerate the intended output columns explicitly.",
};
const UNALIASED_CALCULATION: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL022",
    message: "Calculated projection has no stable output name",
    remediation: "Add an explicit AS alias that describes the projected value.",
};
const UNUSED_TABLE_ALIAS: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL023",
    message: "Table alias is never referenced",
    remediation: "Use the alias to qualify references or remove it.",
};
const NULL_REJECTED_LEFT_JOIN: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL024",
    message: "WHERE predicate rejects NULL rows from a LEFT JOIN",
    remediation: "Move the right-side predicate into ON or use INNER JOIN when row rejection is intentional.",
};
const IMPLICIT_INNER_JOIN: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL025",
    message: "JOIN type is implicit",
    remediation: "Write INNER JOIN explicitly.",
};
const AMBIGUOUS_ORDER_DIRECTIONS: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL026",
    message: "ORDER BY mixes explicit and implicit directions",
    remediation: "State ASC or DESC for every ordering expression in this clause.",
};
const UNQUALIFIED_MULTI_SOURCE_COLUMN: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL027",
    message: "Column reference is unqualified in a multi-relation query",
    remediation: "Qualify the column with its relation alias.",
};
const INCONSISTENT_SINGLE_SOURCE_QUALIFICATION: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL028",
    message: "Single-relation query mixes qualified and unqualified columns",
    remediation: "Use one consistent qualification style in this query scope.",
};
const UNKNOWN_RELATION_QUALIFIER: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL029",
    message: "Qualified reference uses a relation absent from this query scope",
    remediation: "Use an available relation alias or add the intended relation to FROM.",
};
const SIMPLE_BOOLEAN_CASE: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL030",
    message: "CASE expression only converts a condition to TRUE or FALSE",
    remediation: "Use a NULL-safe boolean expression directly.",
};
const NESTED_ELSE_CASE: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL031",
    message: "CASE expression is nested directly inside ELSE",
    remediation: "Flatten the nested branch into the surrounding CASE expression.",
};
const UNUSED_JOINED_RELATION: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL032",
    message: "Joined relation contributes no referenced values",
    remediation: "Use the joined relation, remove the join, or suppress this intentional cardinality filter.",
};
const COMMENT_ATTACHMENT: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL033",
    message: "Comment is not attached to the syntax node it explains",
    remediation: "Use a standalone -- comment block immediately above the relevant CTE, JOIN, filter, predicate, selected expression, CASE branch, grouping, or ordering node.",
};
const CTE_ONLY_BODY: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL034",
    message: "Query keeps transformation logic outside top-level CTEs",
    remediation: "Move transformation logic into named top-level CTEs before the terminal SELECT.",
};
const TERMINAL_SELECT: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL035",
    message: "Terminal SELECT does not read plainly from the final top-level CTE",
    remediation: "Name the final logical CTE and leave one terminal SELECT from that CTE.",
};
const NESTED_CTE: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL036",
    message: "CTE is nested inside another query",
    remediation: "Hoist the nested CTE into the statement's top-level WITH list.",
};
const RECURSIVE_CTE: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL037",
    message: "Recursive CTE is not permitted",
    remediation: "Replace recursion with an explicit upstream relation or a bounded non-recursive query shape.",
};
const CROSS_JOIN: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL038",
    message: "CROSS JOIN creates an explicit cartesian product",
    remediation: "Use a keyed JOIN, or suppress this rule with a reason when the cartesian product is intentional.",
};
const TRIVIAL_EQUALITY_TOKEN_COUNT: usize = 3;

const DEFAULT_RULES: [&str; 12] = [
    NULL_COMPARISON.code,
    IMPLICIT_CARTESIAN_JOIN.code,
    JOIN_WITHOUT_CONDITION.code,
    UNORDERED_LIMIT.code,
    UNUSED_CTE.code,
    REDUNDANT_DISTINCT.code,
    POSITIONAL_SET_STAR.code,
    DUPLICATE_TABLE_ALIAS.code,
    DUPLICATE_OUTPUT_ALIAS.code,
    UNSTABLE_ROW_NUMBER.code,
    NULL_NOT_IN.code,
    SET_ARITY_MISMATCH.code,
];

const ALL_RULE_METADATA: [&LintRuleMetadata; 38] = [
    &NULL_COMPARISON,
    &IMPLICIT_CARTESIAN_JOIN,
    &JOIN_WITHOUT_CONDITION,
    &UNORDERED_LIMIT,
    &UNUSED_CTE,
    &REDUNDANT_DISTINCT,
    &POSITIONAL_SET_STAR,
    &EXPLICIT_UNION,
    &DUPLICATE_TABLE_ALIAS,
    &DUPLICATE_OUTPUT_ALIAS,
    &MIXED_GROUP_ORDER_REFERENCES,
    &REDUNDANT_ELSE_NULL,
    &PARENTHESIZED_DISTINCT,
    &CONSTANT_PREDICATE,
    &CONSECUTIVE_SEMICOLON,
    &REDUNDANT_SELF_ALIAS,
    &COUNT_ONE,
    &UNSTABLE_ROW_NUMBER,
    &NULL_NOT_IN,
    &SET_ARITY_MISMATCH,
    &PROJECTED_STAR,
    &UNALIASED_CALCULATION,
    &UNUSED_TABLE_ALIAS,
    &NULL_REJECTED_LEFT_JOIN,
    &IMPLICIT_INNER_JOIN,
    &AMBIGUOUS_ORDER_DIRECTIONS,
    &UNQUALIFIED_MULTI_SOURCE_COLUMN,
    &INCONSISTENT_SINGLE_SOURCE_QUALIFICATION,
    &UNKNOWN_RELATION_QUALIFIER,
    &SIMPLE_BOOLEAN_CASE,
    &NESTED_ELSE_CASE,
    &UNUSED_JOINED_RELATION,
    &COMMENT_ATTACHMENT,
    &CTE_ONLY_BODY,
    &TERMINAL_SELECT,
    &NESTED_CTE,
    &RECURSIVE_CTE,
    &CROSS_JOIN,
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

struct DiagnosticContext<'a> {
    sql: &'a str,
    dialect: DialectType,
    facts: &'a QueryFacts,
    tokens: &'a [Token],
    enabled: &'a HashSet<String>,
}

struct FactBuildOptions<'a> {
    external_identifiers: &'a HashSet<String>,
    allows_ceremonial_select: bool,
}

pub(crate) fn lint_json_impl(request_json: &str) -> Result<String, String> {
    let request: LintRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let response = lint(request)?;
    serde_json::to_string(&response).map_err(|error| error.to_string())
}

pub(crate) fn rule_metadata() -> Vec<LintRuleMetadata> {
    ALL_RULE_METADATA.iter().map(|rule| **rule).collect()
}

fn lint(request: LintRequest) -> Result<LintResponse, String> {
    if request.version != LINT_API_VERSION {
        return Err(format!(
            "unsupported native lint request version {}; expected {LINT_API_VERSION}",
            request.version
        ));
    }
    let enabled = enabled_rules(request.enabled_rules, &request.ignored_rules)?;
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
            complexity_guard: ComplexityGuardOptions {
                max_function_call_depth: Some(MAX_LINT_FUNCTION_CALL_DEPTH),
                ..Default::default()
            },
            ..Default::default()
        },
    );
    let statements = parser.parse().map_err(|error| error.to_string())?;
    let external_identifiers: HashSet<String> = request
        .external_identifiers
        .iter()
        .map(|identifier| identifier.to_ascii_lowercase())
        .collect();
    let options = FactBuildOptions {
        external_identifiers: &external_identifiers,
        allows_ceremonial_select: request.allows_ceremonial_select,
    };
    let facts = build_facts(&statements, &tokens, &request.sql, &options);
    let context = DiagnosticContext {
        sql: &request.sql,
        dialect: dialect_type,
        facts: &facts,
        tokens: &tokens,
        enabled: &enabled,
    };
    let mut diagnostics = diagnostics(&context);
    diagnostics.sort_by_key(|diagnostic| (diagnostic.start, diagnostic.end, diagnostic.code));
    Ok(LintResponse {
        version: LINT_API_VERSION,
        diagnostics,
    })
}

fn enabled_rules(
    requested: Option<Vec<String>>,
    ignored: &[String],
) -> Result<HashSet<String>, String> {
    let selectors =
        requested.unwrap_or_else(|| DEFAULT_RULES.iter().map(ToString::to_string).collect());
    let mut rules = expand_rule_selectors(&selectors)?;
    for code in expand_rule_selectors(ignored)? {
        rules.remove(&code);
    }
    Ok(rules)
}

fn expand_rule_selectors(selectors: &[String]) -> Result<HashSet<String>, String> {
    let mut selected: HashSet<String> = HashSet::new();
    for selector in selectors {
        let matches: Vec<&str> = ALL_RULE_METADATA
            .iter()
            .map(|rule| rule.code)
            .filter(|code| code.starts_with(selector))
            .collect();
        if matches.is_empty() {
            return Err(format!("unknown native lint rule '{selector}'"));
        }
        selected.extend(matches.into_iter().map(ToString::to_string));
    }
    Ok(selected)
}

fn build_facts(
    expressions: &[Expression],
    tokens: &[Token],
    sql: &str,
    options: &FactBuildOptions<'_>,
) -> QueryFacts {
    let mut facts: QueryFacts = collect_token_query_facts(tokens, sql);
    facts.null_comparisons = null_comparison_spans(tokens);
    facts.additional = collect_additional_facts(
        tokens,
        options.external_identifiers,
        options.allows_ceremonial_select,
    );
    for expression in expressions {
        facts
            .unused_cte_names
            .extend(collect_unused_ctes(expression));
    }
    facts
}

fn collect_token_query_facts(tokens: &[Token], sql: &str) -> QueryFacts {
    let mut facts = QueryFacts::default();
    let depths = token_depths(tokens);
    facts = collect_rule_migration_facts(tokens, &depths, sql, facts);
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

fn collect_rule_migration_facts(
    tokens: &[Token],
    depths: &[usize],
    sql: &str,
    mut facts: QueryFacts,
) -> QueryFacts {
    let significant: Vec<usize> = (0..tokens.len())
        .filter(|&index| !is_layout(&tokens[index]) && !is_comment(&tokens[index]))
        .collect();

    for (position, &index) in significant.iter().enumerate() {
        let text = tokens[index].text.as_str();
        if text.eq_ignore_ascii_case("cross")
            && significant
                .get(position + 1)
                .is_some_and(|&next| tokens[next].token_type == TokenType::Join)
        {
            facts.cross_joins.push(tokens[index].span);
        }
        if text.eq_ignore_ascii_case("with") {
            if depths[index] > 0 {
                facts.nested_ctes.push(tokens[index].span);
            }
            if significant
                .get(position + 1)
                .is_some_and(|&next| tokens[next].text.eq_ignore_ascii_case("recursive"))
            {
                facts.recursive_ctes.push(tokens[index].span);
            }
        }
    }

    let (cte_only_bodies, terminal_selects) =
        collect_terminal_shape_facts(tokens, depths, &significant);
    facts.cte_only_bodies.extend(cte_only_bodies);
    facts.terminal_selects.extend(terminal_selects);
    facts
        .invalid_comment_attachments
        .extend(collect_comment_attachment_facts(tokens, sql));
    facts
}

fn collect_terminal_shape_facts(
    tokens: &[Token],
    depths: &[usize],
    significant: &[usize],
) -> (Vec<Span>, Vec<Span>) {
    let mut cte_only_bodies: Vec<Span> = Vec::new();
    let mut terminal_selects: Vec<Span> = Vec::new();
    let Some(root_select_position) = significant
        .iter()
        .rposition(|&index| depths[index] == 0 && tokens[index].token_type == TokenType::Select)
    else {
        return (cte_only_bodies, terminal_selects);
    };
    let root_select = significant[root_select_position];
    let has_top_level_with = significant[..root_select_position]
        .iter()
        .any(|&index| depths[index] == 0 && tokens[index].text.eq_ignore_ascii_case("with"));
    let tail: Vec<usize> = significant[root_select_position + 1..]
        .iter()
        .copied()
        .take_while(|&index| tokens[index].token_type != TokenType::Semicolon)
        .filter(|&index| depths[index] == 0)
        .collect();
    let has_terminal_logic = tail.iter().any(|&index| {
        matches!(
            tokens[index].token_type,
            TokenType::Join
                | TokenType::Where
                | TokenType::Group
                | TokenType::Having
                | TokenType::Qualify
                | TokenType::Order
                | TokenType::Limit
                | TokenType::Offset
                | TokenType::Union
                | TokenType::Intersect
                | TokenType::Except
        )
    });
    if !has_top_level_with || has_terminal_logic {
        cte_only_bodies.push(tokens[root_select].span);
    }
    if !has_top_level_with {
        return (cte_only_bodies, terminal_selects);
    }

    let final_cte = significant[..root_select_position]
        .windows(3)
        .filter(|window| {
            depths[window[0]] == 0
                && is_lint_identifier(&tokens[window[0]])
                && tokens[window[1]].token_type == TokenType::As
                && tokens[window[2]].token_type == TokenType::LParen
        })
        .map(|window| tokens[window[0]].text.to_ascii_lowercase())
        .next_back();
    let from_position = tail.iter().position(|&index| is_query_from(tokens, index));
    let terminal_is_plain = from_position.is_some_and(|position| {
        let projection = &tail[..position];
        let relation = tail.get(position + 1);
        let remainder = &tail[position.saturating_add(2)..];
        !projection.is_empty()
            && plain_terminal_projection(tokens, projection)
            && relation.is_some_and(|&index| {
                final_cte
                    .as_ref()
                    .is_some_and(|name| tokens[index].text.eq_ignore_ascii_case(name))
            })
            && remainder.is_empty()
    });
    if !terminal_is_plain {
        terminal_selects.push(tokens[root_select].span);
    }
    (cte_only_bodies, terminal_selects)
}

fn plain_terminal_projection(tokens: &[Token], projection: &[usize]) -> bool {
    projection.iter().all(|&index| {
        is_lint_identifier(&tokens[index])
            || matches!(
                tokens[index].token_type,
                TokenType::Star | TokenType::Dot | TokenType::Comma | TokenType::As
            )
    })
}

fn is_lint_identifier(token: &Token) -> bool {
    matches!(
        token.token_type,
        TokenType::Identifier | TokenType::QuotedIdentifier | TokenType::Var
    )
}

fn collect_comment_attachment_facts(tokens: &[Token], sql: &str) -> Vec<Span> {
    let mut invalid: Vec<Span> = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        if !token.trailing_comments.is_empty() {
            invalid.push(token.span);
        }
        if token.comments.is_empty() {
            continue;
        }
        let gap_start = index
            .checked_sub(1)
            .map_or(0, |previous| tokens[previous].span.end);
        let gap = char_slice(sql, gap_start, token.span.start).unwrap_or_default();
        let block_comment = gap.contains("/*");
        let detached = gap.replace("\r\n", "\n").ends_with("\n\n");
        let unsupported_target = matches!(
            token.token_type,
            TokenType::Comma
                | TokenType::RParen
                | TokenType::Semicolon
                | TokenType::Then
                | TokenType::Else
                | TokenType::From
        );
        if block_comment || detached || unsupported_target {
            invalid.push(token.span);
        }
    }
    invalid
}

pub(super) fn token_depths(tokens: &[Token]) -> Vec<usize> {
    let mut depth = 0_usize;
    tokens
        .iter()
        .map(|token| {
            let current = depth;
            if matches!(
                token.token_type,
                TokenType::LParen | TokenType::LBracket | TokenType::LBrace
            ) {
                depth += 1;
            } else if matches!(
                token.token_type,
                TokenType::RParen | TokenType::RBracket | TokenType::RBrace
            ) {
                depth = depth.saturating_sub(1);
            }
            current
        })
        .collect()
}

pub(super) fn query_end(tokens: &[Token], depths: &[usize], start: usize, depth: usize) -> usize {
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

pub(super) fn direct_indices(
    depths: &[usize],
    start: usize,
    end: usize,
    depth: usize,
) -> Vec<usize> {
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

pub(super) fn is_query_from(tokens: &[Token], index: usize) -> bool {
    tokens[index].token_type == TokenType::From
        && significant_before(tokens, index)
            .is_none_or(|previous| tokens[previous].token_type != TokenType::Distinct)
}

fn redundant_distinct_span(context: &QueryTokenContext<'_>) -> Option<Span> {
    let QueryTokenContext {
        tokens,
        depths,
        direct,
        query_end,
        depth,
    } = context;
    let group_position = group_by_position(tokens, direct)?;
    let group_index = direct[group_position];
    let projection_end = direct
        .iter()
        .copied()
        .find(|&index| is_query_from(tokens, index))
        .filter(|index| *index < group_index)
        .unwrap_or(group_index);
    let distinct_position = direct.iter().position(|&index| {
        index < projection_end && tokens[index].token_type == TokenType::Distinct
    })?;
    if direct
        .get(distinct_position + 1)
        .is_some_and(|&index| tokens[index].token_type == TokenType::On)
    {
        return None;
    }
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
        .position(|&index| is_query_from(tokens, index))
    else {
        return (implicit, missing_conditions);
    };
    let clause_end = direct[from_position + 1..]
        .iter()
        .position(|&index| is_post_from_clause(tokens[index].token_type))
        .map_or(direct.len(), |offset| from_position + 1 + offset);
    let relation_clause = &direct[from_position + 1..clause_end];
    let values_relation = relation_clause
        .first()
        .is_some_and(|&index| tokens[index].token_type == TokenType::Values);
    for (position, &index) in relation_clause.iter().enumerate() {
        if tokens[index].token_type == TokenType::Comma
            && !values_relation
            && relation_clause
                .get(position + 1)
                .is_none_or(|&next| tokens[next].token_type != TokenType::Lateral)
        {
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
        .take_while(|&index| depths[index] != range.depth || !is_query_from(tokens, index))
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

fn null_comparison_fix(tokens: &[Token], span: Span) -> Option<LintEdit> {
    let index = token_index_for_span(tokens, span)?;
    let token = &tokens[index];
    if !adjacent_null(tokens, index, true) {
        return None;
    }
    let replacement = match token.token_type {
        TokenType::Eq => "IS",
        TokenType::Neq => "IS NOT",
        _ => return None,
    };
    Some(LintEdit {
        start: span.start,
        end: span.end,
        replacement: replacement.to_string(),
    })
}

fn redundant_distinct_fix(tokens: &[Token], span: Span) -> LintEdit {
    let end = token_index_for_span(tokens, span)
        .and_then(|index| significant_after(tokens, index))
        .filter(|&index| !is_comment(&tokens[index]))
        .map_or(span.end, |index| tokens[index].span.start);
    LintEdit {
        start: span.start,
        end,
        replacement: String::new(),
    }
}

fn implicit_cartesian_fix(sql: &str, tokens: &[Token], span: Span) -> Option<LintEdit> {
    let comma_index = token_index_for_span(tokens, span)?;
    let depths = token_depths(tokens);
    let depth = depths[comma_index];
    let from_index = (0..comma_index).rev().find(|&index| {
        depths[index] == depth
            && (is_query_from(tokens, index) || tokens[index].token_type == TokenType::Semicolon)
    })?;
    if !is_query_from(tokens, from_index) {
        return None;
    }
    let clause_end = (comma_index + 1..tokens.len())
        .find(|&index| depths[index] == depth && is_post_from_clause(tokens[index].token_type))
        .unwrap_or(tokens.len());
    if tokens[from_index + 1..clause_end]
        .iter()
        .any(|token| token.token_type == TokenType::Join)
    {
        return None;
    }
    let next_index = significant_after(tokens, comma_index)?;
    let end = tokens[next_index].span.start;
    let replaced = char_slice(sql, span.start, end)?;
    if contains_comment(replaced) {
        return None;
    }
    Some(LintEdit {
        start: span.start,
        end,
        replacement: " CROSS JOIN ".to_string(),
    })
}

fn conditionless_join_fix(tokens: &[Token], span: Span) -> Option<LintEdit> {
    let join_index = token_index_for_span(tokens, span)?;
    let depths = token_depths(tokens);
    let depth = depths[join_index];
    if significant_before(tokens, join_index).is_some_and(|index| {
        matches!(
            tokens[index].text.to_ascii_uppercase().as_str(),
            "INNER"
                | "LEFT"
                | "RIGHT"
                | "FULL"
                | "OUTER"
                | "CROSS"
                | "NATURAL"
                | "ASOF"
                | "SEMI"
                | "ANTI"
        )
    }) {
        return None;
    }
    let condition_end = (join_index + 1..tokens.len())
        .find(|&index| {
            depths[index] == depth
                && (tokens[index].token_type == TokenType::Join
                    || is_post_from_clause(tokens[index].token_type))
        })
        .unwrap_or(tokens.len());
    if tokens[join_index + 1..condition_end]
        .iter()
        .any(|token| matches!(token.token_type, TokenType::On | TokenType::Using))
    {
        return None;
    }
    Some(LintEdit {
        start: span.start,
        end: span.end,
        replacement: "CROSS JOIN".to_string(),
    })
}

fn unused_cte_fix(sql: &str, tokens: &[Token], name_span: Span) -> Option<LintEdit> {
    let name_index = token_index_for_span(tokens, name_span)?;
    if tokens[name_index].text.starts_with("__") {
        return None;
    }
    let as_index = significant_after(tokens, name_index)?;
    if tokens[as_index].token_type != TokenType::As {
        return None;
    }
    let open_index = significant_after(tokens, as_index)?;
    if tokens[open_index].token_type != TokenType::LParen {
        return None;
    }
    let depths = token_depths(tokens);
    let close_depth = depths[open_index] + 1;
    let close_index = (open_index + 1..tokens.len()).find(|&index| {
        tokens[index].token_type == TokenType::RParen && depths[index] == close_depth
    })?;
    let body_tokens = &tokens[open_index + 1..close_index];
    let first_body = body_tokens.iter().find(|token| !is_layout(token))?;
    if !matches!(first_body.token_type, TokenType::Select | TokenType::With)
        || body_tokens.iter().any(|token| {
            matches!(
                token.text.to_ascii_uppercase().as_str(),
                "INSERT" | "UPDATE" | "DELETE" | "MERGE"
            )
        })
    {
        return None;
    }
    let previous_index = significant_before(tokens, name_index)?;
    let next_index = significant_after(tokens, close_index)?;
    let (start, end) = if tokens[next_index].token_type == TokenType::Comma {
        let following_index = significant_after(tokens, next_index)?;
        (name_span.start, tokens[following_index].span.start)
    } else if tokens[previous_index].token_type == TokenType::Comma {
        (
            tokens[previous_index].span.start,
            tokens[close_index].span.end,
        )
    } else if tokens[previous_index].token_type == TokenType::With {
        (
            tokens[previous_index].span.start,
            tokens[next_index].span.start,
        )
    } else {
        return None;
    };
    if contains_comment(char_slice(sql, start, end)?) {
        return None;
    }
    Some(LintEdit {
        start,
        end,
        replacement: String::new(),
    })
}

fn token_index_for_span(tokens: &[Token], span: Span) -> Option<usize> {
    tokens.iter().position(|token| token.span == span)
}

pub(super) fn significant_before(tokens: &[Token], index: usize) -> Option<usize> {
    (0..index)
        .rev()
        .find(|&candidate| !is_layout(&tokens[candidate]))
}

pub(super) fn significant_after(tokens: &[Token], index: usize) -> Option<usize> {
    (index + 1..tokens.len()).find(|&candidate| !is_layout(&tokens[candidate]))
}

pub(super) fn is_layout(token: &Token) -> bool {
    matches!(token.token_type, TokenType::Space | TokenType::Break)
}

pub(super) fn is_comment(token: &Token) -> bool {
    matches!(
        token.token_type,
        TokenType::LineComment | TokenType::BlockComment
    )
}

fn diagnostics(context: &DiagnosticContext<'_>) -> Vec<LintDiagnostic> {
    let mut output: Vec<LintDiagnostic> = core_diagnostics(context);
    output.extend(additional_style_diagnostics(context));
    output.extend(additional_relation_diagnostics(context));
    output.extend(rule_migration_diagnostics(context));
    output
}

fn core_diagnostics(context: &DiagnosticContext<'_>) -> Vec<LintDiagnostic> {
    let DiagnosticContext {
        sql,
        dialect,
        facts,
        tokens,
        enabled,
    } = context;
    let mut diagnostics: Vec<LintDiagnostic> = Vec::new();
    if enabled.contains(NULL_COMPARISON.code) {
        diagnostics.extend(facts.null_comparisons.iter().map(|span| {
            let fix = null_comparison_fix(tokens, *span);
            diagnostic(
                &NULL_COMPARISON,
                Some(*span),
                fix,
                Some("only equality and inequality comparisons have a deterministic repair"),
            )
        }));
    }
    if enabled.contains(IMPLICIT_CARTESIAN_JOIN.code) {
        diagnostics.extend(facts.implicit_cartesian_joins.iter().map(|span| {
            let fix = implicit_cartesian_fix(sql, tokens, *span);
            diagnostic(
                &IMPLICIT_CARTESIAN_JOIN,
                Some(*span),
                fix,
                Some("mixed joins, comments, or generated SQL require an explicit authored repair"),
            )
        }));
    }
    if enabled.contains(JOIN_WITHOUT_CONDITION.code) {
        diagnostics.extend(facts.joins_without_condition.iter().map(|span| {
            let fix = conditionless_join_fix(tokens, *span);
            diagnostic(
                &JOIN_WITHOUT_CONDITION,
                Some(*span),
                fix,
                Some("qualified joins or joins with placeholder conditions require user intent"),
            )
        }));
    }
    if enabled.contains(UNORDERED_LIMIT.code) {
        diagnostics.extend(diagnostics_for_spans(
            &UNORDERED_LIMIT,
            &facts.unordered_limits,
            Some("deterministic ordering columns and tie-breakers require user intent"),
        ));
    }
    if enabled.contains(UNUSED_CTE.code) {
        for span in unused_cte_spans(tokens, &facts.unused_cte_names) {
            let fix = unused_cte_fix(sql, tokens, span);
            diagnostics.push(diagnostic(
                &UNUSED_CTE,
                Some(span),
                fix,
                Some("only contiguous authored, comment-free, select-only CTEs can be removed"),
            ));
        }
    }
    if enabled.contains(REDUNDANT_DISTINCT.code) {
        diagnostics.extend(facts.redundant_distincts.iter().map(|span| {
            diagnostic(
                &REDUNDANT_DISTINCT,
                Some(*span),
                Some(redundant_distinct_fix(tokens, *span)),
                None,
            )
        }));
    }
    if enabled.contains(POSITIONAL_SET_STAR.code) {
        diagnostics.extend(diagnostics_for_spans(
            &POSITIONAL_SET_STAR,
            &facts.positional_set_stars,
            Some(
                "column names and their intended positional order require resolved schema evidence",
            ),
        ));
    }
    if enabled.contains(EXPLICIT_UNION.code) {
        diagnostics.extend(facts.additional.bare_unions.iter().map(|span| {
            let fix = explicit_union_fix(*dialect, *span);
            diagnostic(
                &EXPLICIT_UNION,
                Some(*span),
                fix,
                Some("the active dialect does not accept explicit UNION DISTINCT"),
            )
        }));
    }
    diagnostics
}

fn additional_style_diagnostics(context: &DiagnosticContext<'_>) -> Vec<LintDiagnostic> {
    let DiagnosticContext {
        sql,
        facts,
        enabled,
        ..
    } = context;
    let mut diagnostics: Vec<LintDiagnostic> = Vec::new();
    if enabled.contains(DUPLICATE_TABLE_ALIAS.code) {
        diagnostics.extend(diagnostics_for_spans(
            &DUPLICATE_TABLE_ALIAS,
            &facts.additional.duplicate_table_aliases,
            Some("choosing a new relation alias requires user intent"),
        ));
    }
    if enabled.contains(DUPLICATE_OUTPUT_ALIAS.code) {
        diagnostics.extend(diagnostics_for_spans(
            &DUPLICATE_OUTPUT_ALIAS,
            &facts.additional.duplicate_output_aliases,
            Some("choosing a stable output name requires user intent"),
        ));
    }
    if enabled.contains(MIXED_GROUP_ORDER_REFERENCES.code) {
        diagnostics.extend(diagnostics_for_spans(
            &MIXED_GROUP_ORDER_REFERENCES,
            &facts.additional.mixed_group_order_references,
            Some("normalization requires reliable projection-name resolution"),
        ));
    }
    if enabled.contains(REDUNDANT_ELSE_NULL.code) {
        diagnostics.extend(facts.additional.redundant_else_nulls.iter().map(|span| {
            diagnostic(
                &REDUNDANT_ELSE_NULL,
                Some(*span),
                Some(deletion(*span)),
                None,
            )
        }));
    }
    if enabled.contains(PARENTHESIZED_DISTINCT.code) {
        diagnostics.extend(facts.additional.parenthesized_distincts.iter().map(|span| {
            diagnostic(
                &PARENTHESIZED_DISTINCT,
                Some(*span),
                parenthesized_distinct_fix(sql, *span),
                Some("comments or malformed parentheses prevent a lossless rewrite"),
            )
        }));
    }
    if enabled.contains(CONSTANT_PREDICATE.code) {
        diagnostics.extend(diagnostics_for_spans(
            &CONSTANT_PREDICATE,
            &facts.additional.constant_predicates,
            Some("removing or replacing a scaffold predicate requires user intent"),
        ));
    }
    if enabled.contains(CONSECUTIVE_SEMICOLON.code) {
        diagnostics.extend(facts.additional.consecutive_semicolons.iter().map(|span| {
            diagnostic(
                &CONSECUTIVE_SEMICOLON,
                Some(*span),
                Some(deletion(*span)),
                None,
            )
        }));
    }
    if enabled.contains(REDUNDANT_SELF_ALIAS.code) {
        diagnostics.extend(facts.additional.redundant_self_aliases.iter().map(|span| {
            diagnostic(
                &REDUNDANT_SELF_ALIAS,
                Some(*span),
                Some(deletion(*span)),
                None,
            )
        }));
    }
    if enabled.contains(COUNT_ONE.code) {
        diagnostics.extend(facts.additional.count_one_literals.iter().map(|span| {
            diagnostic(
                &COUNT_ONE,
                Some(*span),
                Some(LintEdit {
                    start: span.start,
                    end: span.end,
                    replacement: "*".to_string(),
                }),
                None,
            )
        }));
    }
    if enabled.contains(UNSTABLE_ROW_NUMBER.code) {
        diagnostics.extend(diagnostics_for_spans(
            &UNSTABLE_ROW_NUMBER,
            &facts.additional.unstable_row_numbers,
            Some("ordering columns and a stable tie-breaker require user intent"),
        ));
    }
    diagnostics
}

fn additional_relation_diagnostics(context: &DiagnosticContext<'_>) -> Vec<LintDiagnostic> {
    let DiagnosticContext {
        sql,
        facts,
        tokens,
        enabled,
        ..
    } = context;
    let mut diagnostics: Vec<LintDiagnostic> = Vec::new();
    if enabled.contains(NULL_NOT_IN.code) {
        diagnostics.extend(diagnostics_for_spans(
            &NULL_NOT_IN,
            &facts.additional.null_not_in_predicates,
            Some("the intended NULL and anti-join semantics require user intent"),
        ));
    }
    if enabled.contains(SET_ARITY_MISMATCH.code) {
        diagnostics.extend(diagnostics_for_spans(
            &SET_ARITY_MISMATCH,
            &facts.additional.set_arity_mismatches,
            Some("the intended branch schema requires user intent"),
        ));
    }
    if enabled.contains(PROJECTED_STAR.code) {
        diagnostics.extend(diagnostics_for_spans(
            &PROJECTED_STAR,
            &facts.additional.projected_stars,
            Some("column enumeration requires reliable resolved schema evidence"),
        ));
    }
    if enabled.contains(UNALIASED_CALCULATION.code) {
        diagnostics.extend(diagnostics_for_spans(
            &UNALIASED_CALCULATION,
            &facts.additional.unaliased_calculations,
            Some("a meaningful stable output name requires user intent"),
        ));
    }
    if enabled.contains(UNUSED_TABLE_ALIAS.code) {
        diagnostics.extend(facts.additional.unused_table_aliases.iter().map(|span| {
            diagnostic(
                &UNUSED_TABLE_ALIAS,
                Some(*span),
                Some(deletion(*span)),
                None,
            )
        }));
    }
    if enabled.contains(NULL_REJECTED_LEFT_JOIN.code) {
        diagnostics.extend(diagnostics_for_spans(
            &NULL_REJECTED_LEFT_JOIN,
            &facts.additional.null_rejected_left_joins,
            Some("moving the predicate or changing join type requires user intent"),
        ));
    }
    if enabled.contains(IMPLICIT_INNER_JOIN.code) {
        diagnostics.extend(facts.additional.implicit_inner_joins.iter().map(|span| {
            diagnostic(
                &IMPLICIT_INNER_JOIN,
                Some(*span),
                Some(LintEdit {
                    start: span.start,
                    end: span.end,
                    replacement: "INNER JOIN".to_string(),
                }),
                None,
            )
        }));
    }
    if enabled.contains(AMBIGUOUS_ORDER_DIRECTIONS.code) {
        diagnostics.extend(diagnostics_for_spans(
            &AMBIGUOUS_ORDER_DIRECTIONS,
            &facts.additional.ambiguous_order_directions,
            Some("normalizing every expression requires a multi-range authored rewrite"),
        ));
    }
    if enabled.contains(UNQUALIFIED_MULTI_SOURCE_COLUMN.code) {
        diagnostics.extend(diagnostics_for_spans(
            &UNQUALIFIED_MULTI_SOURCE_COLUMN,
            &facts.additional.unqualified_multi_source_columns,
            Some("choosing the correct relation qualifier requires user intent"),
        ));
    }
    if enabled.contains(INCONSISTENT_SINGLE_SOURCE_QUALIFICATION.code) {
        diagnostics.extend(diagnostics_for_spans(
            &INCONSISTENT_SINGLE_SOURCE_QUALIFICATION,
            &facts.additional.inconsistent_single_source_qualification,
            Some("qualification style is normalized by the canonical formatter only when safe"),
        ));
    }
    if enabled.contains(UNKNOWN_RELATION_QUALIFIER.code) {
        diagnostics.extend(diagnostics_for_spans(
            &UNKNOWN_RELATION_QUALIFIER,
            &facts.additional.unknown_relation_qualifiers,
            Some("the intended relation or alias requires user intent"),
        ));
    }
    if enabled.contains(SIMPLE_BOOLEAN_CASE.code) {
        diagnostics.extend(facts.additional.simple_boolean_cases.iter().map(|span| {
            diagnostic(
                &SIMPLE_BOOLEAN_CASE,
                Some(*span),
                simple_boolean_case_fix(sql, tokens, *span),
                Some("comments or a non-canonical CASE shape prevent a lossless rewrite"),
            )
        }));
    }
    if enabled.contains(NESTED_ELSE_CASE.code) {
        diagnostics.extend(diagnostics_for_spans(
            &NESTED_ELSE_CASE,
            &facts.additional.nested_else_cases,
            Some("flattening nested branches requires a multi-range authored rewrite"),
        ));
    }
    if enabled.contains(UNUSED_JOINED_RELATION.code) {
        diagnostics.extend(diagnostics_for_spans(
            &UNUSED_JOINED_RELATION,
            &facts.additional.unused_joined_relations,
            Some("the join may intentionally filter or multiply rows"),
        ));
    }
    diagnostics
}

fn rule_migration_diagnostics(context: &DiagnosticContext<'_>) -> Vec<LintDiagnostic> {
    let DiagnosticContext { facts, enabled, .. } = context;
    let mut diagnostics: Vec<LintDiagnostic> = Vec::new();
    if enabled.contains(COMMENT_ATTACHMENT.code) {
        diagnostics.extend(diagnostics_for_spans(
            &COMMENT_ATTACHMENT,
            &facts.invalid_comment_attachments,
            Some("comment attachment requires an authored placement decision"),
        ));
    }
    if enabled.contains(CTE_ONLY_BODY.code) {
        diagnostics.extend(diagnostics_for_spans(
            &CTE_ONLY_BODY,
            &facts.cte_only_bodies,
            Some("extracting transformation logic into named CTEs requires user intent"),
        ));
    }
    if enabled.contains(TERMINAL_SELECT.code) {
        diagnostics.extend(diagnostics_for_spans(
            &TERMINAL_SELECT,
            &facts.terminal_selects,
            Some("choosing the final logical CTE and projection requires user intent"),
        ));
    }
    if enabled.contains(NESTED_CTE.code) {
        diagnostics.extend(diagnostics_for_spans(
            &NESTED_CTE,
            &facts.nested_ctes,
            Some("hoisting a nested CTE requires an authored query rewrite"),
        ));
    }
    if enabled.contains(RECURSIVE_CTE.code) {
        diagnostics.extend(diagnostics_for_spans(
            &RECURSIVE_CTE,
            &facts.recursive_ctes,
            Some("replacing recursion requires an authored query design"),
        ));
    }
    if enabled.contains(CROSS_JOIN.code) {
        diagnostics.extend(diagnostics_for_spans(
            &CROSS_JOIN,
            &facts.cross_joins,
            Some("a keyed relationship requires user intent"),
        ));
    }
    diagnostics
}

fn deletion(span: Span) -> LintEdit {
    LintEdit {
        start: span.start,
        end: span.end,
        replacement: String::new(),
    }
}

fn parenthesized_distinct_fix(sql: &str, span: Span) -> Option<LintEdit> {
    let source = char_slice(sql, span.start, span.end)?;
    if contains_comment(source) {
        return None;
    }
    let open = source.find('(')?;
    let close = source.rfind(')')?;
    (open < close).then(|| LintEdit {
        start: span.start,
        end: span.end,
        replacement: format!("DISTINCT {}", &source[open + 1..close]),
    })
}

fn simple_boolean_case_fix(sql: &str, tokens: &[Token], span: Span) -> Option<LintEdit> {
    let case_index = token_index_for_span(tokens, span).or_else(|| {
        tokens
            .iter()
            .position(|token| token.span.start == span.start && token.token_type == TokenType::Case)
    })?;
    let end_index = tokens.iter().position(|token| token.span.end == span.end)?;
    let source = char_slice(sql, span.start, span.end)?;
    if contains_comment(source) {
        return None;
    }
    let when_index =
        (case_index + 1..end_index).find(|&index| tokens[index].token_type == TokenType::When)?;
    let then_index =
        (when_index + 1..end_index).find(|&index| tokens[index].token_type == TokenType::Then)?;
    let condition = char_slice(
        sql,
        tokens[when_index].span.end,
        tokens[then_index].span.start,
    )?
    .trim();
    (!condition.is_empty()).then(|| LintEdit {
        start: span.start,
        end: span.end,
        replacement: format!("COALESCE({condition}, FALSE)"),
    })
}

fn explicit_union_fix(dialect: DialectType, span: Span) -> Option<LintEdit> {
    matches!(
        dialect,
        DialectType::Generic
            | DialectType::PostgreSQL
            | DialectType::MySQL
            | DialectType::BigQuery
            | DialectType::Snowflake
            | DialectType::DuckDB
            | DialectType::Hive
            | DialectType::Spark
            | DialectType::Trino
            | DialectType::Presto
            | DialectType::Redshift
            | DialectType::ClickHouse
            | DialectType::Databricks
            | DialectType::Athena
    )
    .then(|| LintEdit {
        start: span.start,
        end: span.end,
        replacement: "UNION DISTINCT".to_string(),
    })
}

fn char_slice(sql: &str, start: usize, end: usize) -> Option<&str> {
    if start > end {
        return None;
    }
    let byte_start = char_offset_to_byte_offset(sql, start)?;
    let byte_end = char_offset_to_byte_offset(sql, end)?;
    sql.get(byte_start..byte_end)
}

fn char_offset_to_byte_offset(sql: &str, offset: usize) -> Option<usize> {
    if offset == sql.chars().count() {
        return Some(sql.len());
    }
    sql.char_indices()
        .nth(offset)
        .map(|(byte_offset, _)| byte_offset)
}

fn contains_comment(source: &str) -> bool {
    source.contains("--") || source.contains("/*")
}

fn diagnostics_for_spans(
    rule: &LintRuleMetadata,
    spans: &[Span],
    fix_unavailable_reason: Option<&'static str>,
) -> Vec<LintDiagnostic> {
    spans
        .iter()
        .map(|span| diagnostic(rule, Some(*span), None, fix_unavailable_reason))
        .collect()
}

fn diagnostic(
    rule: &LintRuleMetadata,
    span: Option<Span>,
    fix: Option<LintEdit>,
    fix_unavailable_reason: Option<&'static str>,
) -> LintDiagnostic {
    let span = span.unwrap_or_default();
    LintDiagnostic {
        code: rule.code,
        message: rule.message,
        remediation: rule.remediation,
        start: span.start,
        end: span.end,
        fix_unavailable_reason: fix.is_none().then_some(fix_unavailable_reason).flatten(),
        fix,
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
