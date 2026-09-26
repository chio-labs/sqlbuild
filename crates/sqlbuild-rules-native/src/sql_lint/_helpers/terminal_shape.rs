use crate::query_analysis::models::CteSlotUsage;
use crate::sql_lint::_helpers::engine::{
    char_slice, contains_comment, is_ceremonial_cte_name, is_comment, is_layout, token_depths,
};
use crate::sql_lint::models::{
    CteBodyLocation, LintDiagnostic, LintEdit, LintRuleMetadata, UnusedOutputContext,
};
use polyglot_sql::expressions::{Column, Identifier, Literal, Select};
use polyglot_sql::optimizer::normalize_identifiers::{
    get_normalization_strategy, normalize_identifier,
};
use polyglot_sql::tokens::{Span, Token, TokenType};
use polyglot_sql::{Dialect, DialectType, Expression, ExpressionWalk};

const CEREMONIAL_SELECT_LITERAL: &str = "1";

pub(super) const UNUSED_CTE_OUTPUT: LintRuleMetadata = LintRuleMetadata {
    code: "SQBRSQL042",
    message: "CTE output column is never read by a later query scope",
    remediation: "Remove the unused output column with format --fix. Keep grouping expressions in GROUP BY; restructure dependencies when no safe edit is available.",
};

pub(super) fn unused_cte_spans(tokens: &[Token], unused_names: &[String]) -> Vec<Span> {
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

pub(super) fn unused_outputs(
    context: UnusedOutputContext<'_>,
) -> Result<Vec<LintDiagnostic>, String> {
    let tokens: Vec<Token> = context
        .tokens
        .iter()
        .filter(|token| !is_layout(token) && !is_comment(token))
        .cloned()
        .collect();
    let context = UnusedOutputContext {
        tokens: &tokens,
        ..context
    };
    let depths = token_depths(&tokens);
    let locations = cte_locations(&tokens, &depths, context.dialect);
    let mut diagnostics: Vec<LintDiagnostic> = Vec::new();
    for statement in context.statements {
        for cte in crate::query_analysis::cte_usage::analyze_with_exemptions(
            statement,
            context.schema,
            context.dialect,
            |cte| {
                context.fixtures && is_ceremonial_cte_name(&cte.alias.name.to_ascii_lowercase())
                    || dependency_import(&cte.this, &context)
            },
        )? {
            if cte.model_output
                || cte.set_operation
                || context.fixtures && is_ceremonial_cte_name(&cte.name.to_ascii_lowercase())
                || dependency_import(&cte.original.this, &context)
            {
                continue;
            }
            let location = locate_cte(&cte, &locations, &context);
            for (ordinal, slot) in cte
                .slots
                .iter()
                .enumerate()
                .filter(|(_, slot)| !slot.read && !slot.semantically_required)
            {
                let planned = location
                    .ok_or("Cannot map this scoped CTE to one contiguous authored definition")
                    .and_then(|location| output_edit(&cte, ordinal, location, &context));
                let (fix, reason) = match planned {
                    Ok(edit) => (Some(edit), None),
                    Err(reason) => (None, Some(reason)),
                };
                let span = fix
                    .as_ref()
                    .map(|fix| (fix.start, fix.end))
                    .unwrap_or_else(|| {
                        location.map_or((0, 0), |location| {
                            (location.name_span.start, location.name_span.end)
                        })
                    });
                diagnostics.push(LintDiagnostic {
                    code: UNUSED_CTE_OUTPUT.code,
                    message: format!("CTE '{}' output '{}' (slot {}) is never read by a later query scope", cte.name, slot.name, ordinal + 1),
                    remediation: if cte.distinct { "This unused DISTINCT output still affects deduplication. Make deduplication independent of the column, or restructure the CTE; no autofix is safe." } else { UNUSED_CTE_OUTPUT.remediation },
                    start: span.0, end: span.1, fix, fix_unavailable_reason: reason,
                });
            }
        }
    }
    Ok(diagnostics)
}

fn dependency_import(expression: &Expression, context: &UnusedOutputContext<'_>) -> bool {
    let Expression::Select(select) = expression else {
        return false;
    };
    if select.expressions.len() != 1
        || !matches!(&select.expressions[0], Expression::Star(star) if star.except.is_none() && star.replace.is_none() && star.rename.is_none())
        || !select.joins.is_empty()
        || select.where_clause.is_some()
        || select.group_by.is_some()
        || select.having.is_some()
        || select.qualify.is_some()
        || select.order_by.is_some()
        || select.limit.is_some()
        || select.offset.is_some()
        || select.fetch.is_some()
        || select.top.is_some()
        || select.sample.is_some()
        || select.with.is_some()
        || select.distinct
    {
        return false;
    }
    let Some(from) = &select.from else {
        return false;
    };
    from.expressions.len() == 1
        && matches!(&from.expressions[0], Expression::Table(table)
        if context.dependency_identifiers.contains(&table.name.name.to_ascii_lowercase()))
}

fn cte_locations(tokens: &[Token], depths: &[usize], dialect: DialectType) -> Vec<CteBodyLocation> {
    let mut locations: Vec<CteBodyLocation> = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        if token.token_type != TokenType::With {
            continue;
        }
        let mut name = index + 1;
        while let Some(open) = cte_body_open(tokens, depths, name) {
            let Some(close) = (open + 1..tokens.len()).find(|&index| {
                depths[index] == depths[open] + 1 && tokens[index].token_type == TokenType::RParen
            }) else {
                break;
            };
            let identifier = if tokens[name].token_type == TokenType::QuotedIdentifier {
                Identifier::quoted(&tokens[name].text)
            } else {
                Identifier::new(&tokens[name].text)
            };
            locations.push(CteBodyLocation {
                name: normalize_identifier(identifier, get_normalization_strategy(Some(dialect)))
                    .name,
                name_span: tokens[name].span,
                open,
                close,
            });
            if tokens
                .get(close + 1)
                .is_none_or(|token| token.token_type != TokenType::Comma)
            {
                break;
            }
            name = close + 2;
        }
    }
    locations
}

fn locate_cte<'a>(
    cte: &CteSlotUsage,
    locations: &'a [CteBodyLocation],
    context: &UnusedOutputContext<'_>,
) -> Option<&'a CteBodyLocation> {
    let tokens = context.tokens;
    let candidates: Vec<&CteBodyLocation> = locations
        .iter()
        .filter(|location| location.name == normalize_identifier(cte.original.alias.clone(), get_normalization_strategy(Some(context.dialect))).name)
        .collect();
    if candidates.len() == 1 {
        return candidates.first().copied();
    }
    let dialect = Dialect::get(context.dialect);
    let expected = match dialect.generate(&cte.original.this) {
        Ok(sql) => sql,
        Err(_) => return None,
    };
    let matching: Vec<&CteBodyLocation> = candidates
        .into_iter()
        .filter(|location| {
            let Some(sql) = char_slice(
                context.sql,
                tokens[location.open].span.end,
                tokens[location.close].span.start,
            ) else {
                return false;
            };
            let Ok(mut expressions) = polyglot_sql::parse(sql, context.dialect) else {
                return false;
            };
            if expressions.len() != 1 {
                return false;
            }
            let expression = expressions.remove(0);
            dialect
                .generate(&expression)
                .is_ok_and(|sql| sql == expected)
        })
        .collect();
    (matching.len() == 1).then(|| matching[0])
}

fn output_edit(
    cte: &CteSlotUsage,
    ordinal: usize,
    location: &CteBodyLocation,
    context: &UnusedOutputContext<'_>,
) -> Result<LintEdit, &'static str> {
    let tokens = context.tokens;
    if cte.distinct {
        return Err(
            "DISTINCT depends on every output column; deduplication must be restructured manually",
        );
    }
    if !cte.original.columns.is_empty() {
        return Err("Remove the corresponding explicit CTE column alias together with this output");
    }
    let Expression::Select(select) = &cte.original.this else {
        return Err("This CTE does not have an editable SELECT projection");
    };
    if select.top.is_some() || select.kind.is_some() || !select.operation_modifiers.is_empty() {
        return Err("SELECT modifiers require an explicit projection rewrite");
    }
    if positional_clauses(select) {
        return Err(
            "Expand positional clauses and GROUP BY ALL to explicit expressions before dropping this output",
        );
    }
    if select.group_by.is_none()
        && select
            .expressions
            .get(ordinal)
            .is_some_and(contains_aggregate)
    {
        return Err(
            "An aggregate projection may establish the CTE row grain; preserve explicit grouping before removing it",
        );
    }
    if cte.slots.len() <= 1 {
        return Err(
            "Removing the final projection would change row semantics; remove or restructure the CTE",
        );
    }
    let ranges = projection_ranges(tokens, location)
        .ok_or("Cannot identify a contiguous SELECT projection list")?;
    if ranges.len() == cte.slots.len() && referenced_local_alias(select, ordinal) {
        return Err("Expand references to this output alias in local clauses before removing it");
    }
    let (start, end, replacement) = if ranges.len() == cte.slots.len() {
        let (first, last) = ranges[ordinal];
        let (start, end) = if ordinal + 1 < ranges.len() {
            (
                tokens[first].span.start,
                tokens[ranges[ordinal + 1].0].span.start,
            )
        } else {
            (tokens[first - 1].span.start, tokens[last].span.end)
        };
        (start, end, String::new())
    } else if ranges.len() == 1 && select.expressions.len() == 1 {
        let Expression::Star(star) = &select.expressions[0] else {
            return Err("Expanded projection slots cannot be mapped to authored expressions");
        };
        if star.except.is_some() || star.replace.is_some() || star.rename.is_some() {
            return Err("Rewrite the modified star as explicit columns before removing an output");
        }
        let projections: Result<Vec<String>, _> = cte
            .slots
            .iter()
            .enumerate()
            .filter(|(index, _)| *index != ordinal)
            .map(|(_, slot)| {
                Dialect::get(context.dialect).generate(&Expression::Column(Box::new(Column {
                    name: Identifier::quoted(&slot.name),
                    table: star.table.clone(),
                    join_mark: false,
                    trailing_comments: Vec::new(),
                    span: None,
                    inferred_type: None,
                })))
            })
            .collect();
        (
            tokens[ranges[0].0].span.start,
            tokens[ranges[0].1].span.end,
            projections
                .map_err(|_| "Cannot render bound star outputs in this dialect")?
                .join(", "),
        )
    } else {
        return Err("Expand mixed star projections to explicit columns before removing an output");
    };
    if contains_comment(
        char_slice(context.sql, start, end).ok_or("Invalid authored projection range")?,
    ) {
        return Err("The projection edit would remove a comment; relocate it before fixing");
    }
    Ok(LintEdit {
        start,
        end,
        replacement,
    })
}

fn positional_clauses(select: &Select) -> bool {
    select
        .group_by
        .as_ref()
        .is_some_and(|group| group.all == Some(true) || group.expressions.iter().any(is_ordinal))
        || select.order_by.as_ref().is_some_and(|order| {
            order
                .expressions
                .iter()
                .any(|ordered| is_ordinal(&ordered.this))
        })
}

fn referenced_local_alias(select: &Select, ordinal: usize) -> bool {
    let Some(Expression::Alias(alias)) = select.expressions.get(ordinal) else {
        return false;
    };
    if matches!(&alias.this, Expression::Column(column) if column.table.is_none() && column.name == alias.alias)
    {
        return false;
    }
    select
        .expressions
        .iter()
        .enumerate()
        .filter(|(index, _)| *index != ordinal)
        .map(|(_, expression)| expression)
        .chain(select.group_by.iter().flat_map(|group| &group.expressions))
        .chain(
            select
                .order_by
                .iter()
                .flat_map(|order| &order.expressions)
                .map(|ordered| &ordered.this),
        )
        .chain(select.where_clause.iter().map(|clause| &clause.this))
        .chain(select.having.iter().map(|clause| &clause.this))
        .chain(select.qualify.iter().map(|clause| &clause.this))
        .any(|expression| references_alias(expression, &alias.alias))
}

fn references_alias(expression: &Expression, alias: &Identifier) -> bool {
    expression.dfs().any(|node| matches!(node, Expression::Column(column) if column.table.is_none() && column.name == *alias))
}

fn contains_aggregate(expression: &Expression) -> bool {
    polyglot_sql::scope::walk_in_scope(expression, false).any(polyglot_sql::traversal::is_aggregate)
}

fn is_ordinal(expression: &Expression) -> bool {
    matches!(expression, Expression::Literal(literal) if matches!(literal.as_ref(), Literal::Number(_)))
}

fn projection_ranges(tokens: &[Token], location: &CteBodyLocation) -> Option<Vec<(usize, usize)>> {
    let depths = token_depths(tokens);
    let depth = depths[location.open] + 1;
    let select = (location.open + 1..location.close)
        .find(|&index| depths[index] == depth && tokens[index].token_type == TokenType::Select)?;
    let end = (select + 1..location.close)
        .find(|&index| {
            depths[index] == depth
                && matches!(
                    tokens[index].token_type,
                    TokenType::From
                        | TokenType::Where
                        | TokenType::Group
                        | TokenType::GroupBy
                        | TokenType::Having
                        | TokenType::Qualify
                        | TokenType::Order
                        | TokenType::OrderBy
                        | TokenType::Limit
                        | TokenType::Offset
                        | TokenType::Window
                        | TokenType::Fetch
                        | TokenType::Into
                )
        })
        .unwrap_or(location.close);
    let mut ranges: Vec<(usize, usize)> = Vec::new();
    let mut start = select + 1;
    if tokens.get(start)?.token_type == TokenType::All {
        start += 1;
    }
    for index in start..end {
        if depths[index] == depth && tokens[index].token_type == TokenType::Comma {
            ranges.push((start, index.checked_sub(1)?));
            start = index + 1;
        }
    }
    if start >= end {
        return None;
    }
    ranges.push((start, end - 1));
    Some(ranges)
}

pub(super) fn final_cte_name_spans(tokens: &[Token], depths: &[usize]) -> Vec<Span> {
    let roots = root_with_indices(tokens, depths);
    let mut names: Vec<(usize, bool)> = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        if token.token_type != TokenType::With {
            continue;
        }
        let depth = depths[index];
        let first = names.len();
        let mut next = index + 1;
        if tokens
            .get(next)
            .is_some_and(|token| token.text.eq_ignore_ascii_case("recursive"))
        {
            next += 1;
        }
        loop {
            let name = next;
            let Some(open) = cte_body_open(tokens, depths, name) else {
                break;
            };
            let Some(close) = (open + 1..tokens.len()).find(|&position| {
                depths[position] == depth + 1 && tokens[position].token_type == TokenType::RParen
            }) else {
                break;
            };
            names.push((name, false));
            if tokens
                .get(close + 1)
                .is_none_or(|token| token.token_type != TokenType::Comma)
            {
                break;
            }
            next = close + 2;
        }
        if roots.contains(&index)
            && names.len() > first
            && let Some((_, terminal)) = names.last_mut()
        {
            *terminal = true;
        }
    }
    names
        .into_iter()
        .filter_map(|(index, terminal)| {
            let is_final = tokens[index].text.eq_ignore_ascii_case("final");
            (terminal != is_final).then_some(tokens[index].span)
        })
        .collect()
}

pub(super) fn root_with_indices(tokens: &[Token], depths: &[usize]) -> Vec<usize> {
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
    significant
        .split(|&index| tokens[index].token_type == TokenType::Semicolon)
        .filter_map(|statement| {
            root_query_tokens(tokens, depths, statement)
                .first()
                .copied()
        })
        .filter(|&index| tokens[index].token_type == TokenType::With)
        .collect()
}

fn root_query_tokens<'a>(
    tokens: &[Token],
    depths: &[usize],
    mut significant: &'a [usize],
) -> &'a [usize] {
    while significant
        .last()
        .is_some_and(|&index| tokens[index].token_type == TokenType::Semicolon)
    {
        significant = &significant[..significant.len() - 1];
    }
    while let Some((&first, rest)) = significant.split_first() {
        if tokens[first].token_type != TokenType::LParen
            || rest
                .last()
                .is_none_or(|&index| tokens[index].token_type != TokenType::RParen)
            || rest.iter().any(|&index| depths[index] <= depths[first])
        {
            break;
        }
        significant = &rest[..rest.len() - 1];
    }
    significant
}

fn cte_body_open(tokens: &[Token], depths: &[usize], name: usize) -> Option<usize> {
    let mut position = name + 1;
    if tokens.get(position)?.token_type == TokenType::LParen {
        position = (position + 1..tokens.len()).find(|&index| {
            depths[index] == depths[name] + 1 && tokens[index].token_type == TokenType::RParen
        })? + 1;
    }
    if tokens.get(position)?.token_type != TokenType::As {
        return None;
    }
    position += 1;
    if tokens.get(position)?.token_type == TokenType::Not {
        position += 1;
    }
    if tokens
        .get(position)?
        .text
        .eq_ignore_ascii_case("materialized")
    {
        position += 1;
    }
    (tokens.get(position)?.token_type == TokenType::LParen).then_some(position)
}

pub(super) fn collect_terminal_shape_facts(
    tokens: &[Token],
    depths: &[usize],
    significant: &[usize],
    allows_ceremonial_select: bool,
) -> (Vec<Span>, Vec<Span>) {
    let mut cte_only_bodies: Vec<Span> = Vec::new();
    let mut terminal_selects: Vec<Span> = Vec::new();
    let significant = root_query_tokens(tokens, depths, significant);
    let Some(&first) = significant.first() else {
        return (cte_only_bodies, terminal_selects);
    };
    let root_depth = depths[first];
    let has_top_level_with = significant.iter().any(|&index| {
        depths[index] == root_depth && tokens[index].text.eq_ignore_ascii_case("with")
    });
    let terminal_set_operator = significant.iter().find(|&&index| {
        depths[index] == root_depth
            && matches!(
                tokens[index].token_type,
                TokenType::Union | TokenType::Intersect | TokenType::Except
            )
    });
    if let Some(&operator) = terminal_set_operator {
        cte_only_bodies.push(tokens[operator].span);
        if has_top_level_with {
            terminal_selects.push(tokens[operator].span);
        }
        return (cte_only_bodies, terminal_selects);
    }
    let Some(root_select_position) = significant.iter().position(|&index| {
        depths[index] == root_depth && tokens[index].token_type == TokenType::Select
    }) else {
        return (cte_only_bodies, terminal_selects);
    };
    let root_select = significant[root_select_position];
    let tail: Vec<usize> = significant[root_select_position + 1..]
        .iter()
        .copied()
        .take_while(|&index| tokens[index].token_type != TokenType::Semicolon)
        .filter(|&index| depths[index] == root_depth)
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

    let final_cte = (0..root_select_position)
        .filter(|&position| {
            let index = significant[position];
            depths[index] == root_depth
                && tokens[index].token_type == TokenType::As
                && significant
                    .get(position + 1)
                    .is_some_and(|&next| tokens[next].token_type == TokenType::LParen)
        })
        .filter_map(|position| cte_name_before_as(tokens, significant, position))
        .next_back();
    let from_position = tail
        .iter()
        .position(|&index| is_terminal_from(tokens, significant, index));
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
    let terminal_is_ceremonial = allows_ceremonial_select
        && tail.len() == 1
        && tokens[tail[0]].text == CEREMONIAL_SELECT_LITERAL;
    if !terminal_is_plain && !terminal_is_ceremonial {
        terminal_selects.push(tokens[root_select].span);
    }
    (cte_only_bodies, terminal_selects)
}

fn cte_name_before_as(
    tokens: &[Token],
    significant: &[usize],
    as_position: usize,
) -> Option<String> {
    let previous_position = as_position.checked_sub(1)?;
    let previous = significant[previous_position];
    if is_lint_identifier(&tokens[previous]) || tokens[previous].text.eq_ignore_ascii_case("final")
    {
        return Some(tokens[previous].text.to_ascii_lowercase());
    }
    if tokens[previous].token_type != TokenType::RParen {
        return None;
    }

    let mut balance = 1_usize;
    for position in (0..previous_position).rev() {
        let index = significant[position];
        match tokens[index].token_type {
            TokenType::RParen => balance += 1,
            TokenType::LParen => {
                balance = balance.saturating_sub(1);
                if balance == 0 {
                    let name = position.checked_sub(1).map(|value| significant[value])?;
                    return (is_lint_identifier(&tokens[name])
                        || tokens[name].text.eq_ignore_ascii_case("final"))
                    .then(|| tokens[name].text.to_ascii_lowercase());
                }
            }
            _ => {}
        }
    }
    None
}

fn plain_terminal_projection(tokens: &[Token], projection: &[usize]) -> bool {
    projection.iter().all(|&index| {
        is_terminal_projection_identifier(&tokens[index])
            || matches!(
                tokens[index].token_type,
                TokenType::Star | TokenType::Dot | TokenType::Comma | TokenType::As
            )
    })
}

fn is_terminal_projection_identifier(token: &Token) -> bool {
    is_lint_identifier(token)
        || matches!(
            token.token_type,
            TokenType::Comment
                | TokenType::Date
                | TokenType::Key
                | TokenType::Sequence
                | TokenType::Time
        )
        || (token.token_type == TokenType::Percent && token.text.eq_ignore_ascii_case("percent"))
}

fn is_lint_identifier(token: &Token) -> bool {
    matches!(
        token.token_type,
        TokenType::Identifier | TokenType::QuotedIdentifier | TokenType::Var
    )
}

fn is_terminal_from(tokens: &[Token], significant: &[usize], index: usize) -> bool {
    if tokens[index].token_type != TokenType::From {
        return false;
    }
    significant
        .iter()
        .position(|&candidate| candidate == index)
        .and_then(|position| position.checked_sub(1))
        .is_none_or(|position| tokens[significant[position]].token_type != TokenType::Distinct)
}
