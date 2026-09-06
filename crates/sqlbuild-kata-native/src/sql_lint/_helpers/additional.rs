use std::collections::HashSet;

use polyglot_sql::tokens::{Span, Token, TokenType};

use crate::sql_lint::_helpers::engine::{
    direct_indices, is_comment, is_layout, query_end, significant_after, significant_before,
    token_depths,
};
use crate::sql_lint::models::AdditionalQueryFacts;

const COUNT_ONE_LITERAL: &str = "1";
const QUALIFIED_REFERENCE_LENGTH: usize = 3;
const IMPLICIT_ALIAS_MINIMUM_LENGTH: usize = 2;

struct QuerySlice<'a> {
    tokens: &'a [Token],
    depths: &'a [usize],
    direct: &'a [usize],
    start: usize,
    end: usize,
    depth: usize,
}

pub(super) fn collect_additional_facts(tokens: &[Token]) -> AdditionalQueryFacts {
    let mut facts = AdditionalQueryFacts::default();
    let depths = token_depths(tokens);
    let significant: Vec<usize> = (0..tokens.len())
        .filter(|&index| !is_layout(&tokens[index]) && !is_comment(&tokens[index]))
        .collect();
    for (position, &index) in significant.iter().enumerate() {
        let token = &tokens[index];
        if token.token_type == TokenType::Union
            && significant.get(position + 1).is_none_or(|&next| {
                !matches!(
                    tokens[next].token_type,
                    TokenType::All | TokenType::Distinct | TokenType::By
                )
            })
        {
            facts.bare_unions.push(token.span);
        }
        if token.token_type == TokenType::Else
            && significant
                .get(position + 1)
                .is_some_and(|&next| tokens[next].token_type == TokenType::Null)
        {
            let next = significant[position + 1];
            facts.redundant_else_nulls.push(Span {
                start: token.span.start,
                end: tokens[next].span.end,
                line: token.span.line,
                column: token.span.column,
            });
        }
        if token.token_type == TokenType::Distinct
            && significant
                .get(position + 1)
                .is_some_and(|&next| tokens[next].token_type == TokenType::LParen)
            && let Some(span) =
                parenthesized_distinct_span(tokens, &depths, significant[position + 1])
        {
            facts.parenthesized_distincts.push(span);
        }
        if token.token_type == TokenType::Semicolon
            && significant
                .get(position.wrapping_sub(1))
                .is_some_and(|&previous| tokens[previous].token_type == TokenType::Semicolon)
        {
            facts.consecutive_semicolons.push(token.span);
        }
        if is_identifier(token)
            && let Some((&as_index, &alias_index)) = significant
                .get(position + 1)
                .zip(significant.get(position + 2))
            && tokens[as_index].token_type == TokenType::As
            && is_identifier(&tokens[alias_index])
            && token.token_type == tokens[alias_index].token_type
            && token.text == tokens[alias_index].text
        {
            facts.redundant_self_aliases.push(Span {
                start: token.span.end,
                end: tokens[alias_index].span.end,
                line: tokens[as_index].span.line,
                column: tokens[as_index].span.column,
            });
        }
        if token.text.eq_ignore_ascii_case("COUNT")
            && let Some(span) = count_one_span(tokens, &significant, position)
        {
            facts.count_one_literals.push(span);
        }
        if token.text.eq_ignore_ascii_case("ROW_NUMBER")
            && let Some(span) = unstable_row_number_span(tokens, &depths, index)
        {
            facts.unstable_row_numbers.push(span);
        }
        if token.token_type == TokenType::Not
            && let Some(span) = null_not_in_span(tokens, &depths, &significant, position)
        {
            facts.null_not_in_predicates.push(span);
        }
        if token.token_type == TokenType::Case
            && let Some(span) = simple_boolean_case_span(tokens, &significant, position)
        {
            facts.simple_boolean_cases.push(span);
        }
        if token.token_type == TokenType::Else
            && significant
                .get(position + 1)
                .is_some_and(|&next| tokens[next].token_type == TokenType::Case)
        {
            facts
                .nested_else_cases
                .push(tokens[significant[position + 1]].span);
        }
        if position + 2 < significant.len()
            && constant_predicate(tokens, &significant[position..position + 3])
        {
            facts
                .constant_predicates
                .push(tokens[significant[position + 1]].span);
        }
    }
    let select_facts = collect_select_additional_facts(tokens, &depths);
    facts.duplicate_output_aliases = select_facts.duplicate_output_aliases;
    facts.unaliased_calculations = select_facts.unaliased_calculations;
    facts.projected_stars = select_facts.projected_stars;
    facts.duplicate_table_aliases = select_facts.duplicate_table_aliases;
    facts.unused_table_aliases = select_facts.unused_table_aliases;
    facts.null_rejected_left_joins = select_facts.null_rejected_left_joins;
    facts.implicit_inner_joins = select_facts.implicit_inner_joins;
    facts.unqualified_multi_source_columns = select_facts.unqualified_multi_source_columns;
    facts.inconsistent_single_source_qualification =
        select_facts.inconsistent_single_source_qualification;
    facts.unknown_relation_qualifiers = select_facts.unknown_relation_qualifiers;
    facts.unused_joined_relations = select_facts.unused_joined_relations;
    facts.mixed_group_order_references = select_facts.mixed_group_order_references;
    facts.ambiguous_order_directions = select_facts.ambiguous_order_directions;
    facts.set_arity_mismatches = set_arity_mismatch_spans(tokens, &depths);
    facts
}

fn collect_select_additional_facts(tokens: &[Token], depths: &[usize]) -> AdditionalQueryFacts {
    let mut facts = AdditionalQueryFacts::default();
    for (select_index, token) in tokens.iter().enumerate() {
        if token.token_type != TokenType::Select {
            continue;
        }
        let depth = depths[select_index];
        let end = query_end(tokens, depths, select_index, depth);
        let direct: Vec<usize> = direct_indices(depths, select_index + 1, end, depth)
            .into_iter()
            .filter(|&index| !is_layout(&tokens[index]) && !is_comment(&tokens[index]))
            .collect();
        let from_position = direct
            .iter()
            .position(|&index| tokens[index].token_type == TokenType::From)
            .unwrap_or(direct.len());
        facts
            .duplicate_output_aliases
            .extend(duplicate_alias_spans(tokens, &direct[..from_position]));
        facts
            .unaliased_calculations
            .extend(unaliased_calculation_spans(
                tokens,
                &direct[..from_position],
            ));
        let projection_end = direct.get(from_position).copied().unwrap_or(end);
        facts.projected_stars.extend(
            (select_index + 1..projection_end)
                .filter(|&index| {
                    depths[index] == depth && tokens[index].token_type == TokenType::Star
                })
                .map(|index| tokens[index].span),
        );
        if from_position < direct.len() {
            let clause_end = direct[from_position + 1..]
                .iter()
                .position(|&index| is_after_relation_clause(tokens[index].token_type))
                .map_or(direct.len(), |offset| from_position + 1 + offset);
            facts.duplicate_table_aliases.extend(duplicate_alias_spans(
                tokens,
                &direct[from_position + 1..clause_end],
            ));
            let query_slice = QuerySlice {
                tokens,
                depths,
                direct: &direct[from_position + 1..clause_end],
                start: select_index,
                end,
                depth,
            };
            facts
                .unused_table_aliases
                .extend(unused_alias_spans(&query_slice));
            facts
                .null_rejected_left_joins
                .extend(null_rejected_left_join_spans(tokens, &direct, clause_end));
            facts.implicit_inner_joins.extend(implicit_inner_join_spans(
                tokens,
                &direct[from_position + 1..clause_end],
            ));
            let reference_slice = QuerySlice {
                tokens,
                depths,
                direct: &direct,
                start: from_position,
                end: clause_end,
                depth,
            };
            let reference_facts = collect_reference_facts(&reference_slice);
            facts
                .unqualified_multi_source_columns
                .extend(reference_facts.unqualified_multi_source_columns);
            facts
                .inconsistent_single_source_qualification
                .extend(reference_facts.inconsistent_single_source_qualification);
            facts
                .unknown_relation_qualifiers
                .extend(reference_facts.unknown_relation_qualifiers);
            facts
                .unused_joined_relations
                .extend(reference_facts.unused_joined_relations);
        }
        facts
            .mixed_group_order_references
            .extend(mixed_reference_clause_spans(tokens, &direct));
        facts
            .ambiguous_order_directions
            .extend(ambiguous_order_direction_spans(tokens, &direct));
    }
    facts
}

fn collect_reference_facts(query: &QuerySlice<'_>) -> AdditionalQueryFacts {
    let QuerySlice {
        tokens,
        direct,
        start: from_position,
        end: relation_end,
        ..
    } = query;
    let from_position = *from_position;
    let relation_end = *relation_end;
    let mut facts = AdditionalQueryFacts::default();
    let relations = &direct[from_position + 1..relation_end];
    let relation_count = 1 + relations
        .iter()
        .filter(|&&index| matches!(tokens[index].token_type, TokenType::Join | TokenType::Comma))
        .count();
    let known = relation_names(tokens, relations);
    let references: Vec<usize> = direct[..from_position]
        .iter()
        .chain(direct[relation_end..].iter())
        .copied()
        .collect();
    let qualified: Vec<usize> = references
        .iter()
        .enumerate()
        .filter_map(|(position, &index)| simple_qualifier(tokens, &references, position, index))
        .collect();
    let unqualified: Vec<usize> = references
        .iter()
        .enumerate()
        .filter_map(|(position, &index)| {
            unqualified_reference(tokens, &references, position, index)
        })
        .collect();
    if relation_count > 1 {
        facts
            .unqualified_multi_source_columns
            .extend(unqualified.iter().map(|&index| tokens[index].span));
    } else if !qualified.is_empty() && !unqualified.is_empty() {
        facts
            .inconsistent_single_source_qualification
            .extend(unqualified.iter().map(|&index| tokens[index].span));
    }
    facts.unknown_relation_qualifiers.extend(
        qualified
            .iter()
            .filter(|&&index| !known.contains(&tokens[index].text.to_ascii_lowercase()))
            .map(|&index| tokens[index].span),
    );
    facts
        .unused_joined_relations
        .extend(unused_join_spans(query, &references));
    facts
}

fn simple_qualifier(
    tokens: &[Token],
    references: &[usize],
    position: usize,
    index: usize,
) -> Option<usize> {
    let previous = position.checked_sub(1).map(|value| references[value]);
    let dot = references.get(position + 1).copied();
    let column = references.get(position + 2).copied();
    let following = references.get(position + 3).copied();
    (is_identifier(&tokens[index])
        && previous.is_none_or(|candidate| tokens[candidate].token_type != TokenType::Dot)
        && dot.is_some_and(|candidate| tokens[candidate].token_type == TokenType::Dot)
        && column.is_some_and(|candidate| is_identifier(&tokens[candidate]))
        && following.is_none_or(|candidate| tokens[candidate].token_type != TokenType::Dot))
    .then_some(index)
}

fn unqualified_reference(
    tokens: &[Token],
    references: &[usize],
    position: usize,
    index: usize,
) -> Option<usize> {
    let previous = position.checked_sub(1).map(|value| references[value]);
    let next = references.get(position + 1).copied();
    (is_identifier(&tokens[index])
        && previous.is_none_or(|candidate| {
            !matches!(tokens[candidate].token_type, TokenType::Dot | TokenType::As)
        })
        && next.is_none_or(|candidate| {
            !matches!(
                tokens[candidate].token_type,
                TokenType::Dot | TokenType::LParen
            )
        }))
    .then_some(index)
}

fn relation_names(tokens: &[Token], relation_clause: &[usize]) -> HashSet<String> {
    let mut names: HashSet<String> = HashSet::new();
    for (position, &index) in relation_clause.iter().enumerate() {
        let starts_relation = position == 0
            || matches!(
                tokens[relation_clause[position - 1]].token_type,
                TokenType::Join | TokenType::Comma
            );
        if starts_relation && is_identifier(&tokens[index]) {
            names.insert(tokens[index].text.to_ascii_lowercase());
        }
        if tokens[index].token_type == TokenType::As
            && let Some(&alias) = relation_clause.get(position + 1)
            && is_identifier(&tokens[alias])
        {
            names.insert(tokens[alias].text.to_ascii_lowercase());
        }
    }
    names
}

fn unused_join_spans(query: &QuerySlice<'_>, references: &[usize]) -> Vec<Span> {
    let QuerySlice {
        tokens,
        direct,
        start: from_position,
        end: relation_end,
        ..
    } = query;
    let from_position = *from_position;
    let relation_end = *relation_end;
    let mut spans: Vec<Span> = Vec::new();
    for position in from_position + 1..relation_end {
        let index = direct[position];
        if tokens[index].token_type != TokenType::Join {
            continue;
        }
        let Some(alias) = relation_alias_after_join(tokens, direct, position) else {
            continue;
        };
        let used = references.windows(2).any(|window| {
            tokens[window[0]].text.eq_ignore_ascii_case(&alias)
                && tokens[window[1]].token_type == TokenType::Dot
        });
        if !used {
            spans.push(tokens[index].span);
        }
    }
    spans
}

fn is_after_relation_clause(token_type: TokenType) -> bool {
    matches!(
        token_type,
        TokenType::Where
            | TokenType::Group
            | TokenType::Having
            | TokenType::Qualify
            | TokenType::Order
            | TokenType::Limit
            | TokenType::Offset
            | TokenType::Fetch
            | TokenType::Union
            | TokenType::Intersect
            | TokenType::Except
            | TokenType::Semicolon
    )
}

fn unaliased_calculation_spans(tokens: &[Token], projection: &[usize]) -> Vec<Span> {
    let mut spans: Vec<Span> = Vec::new();
    let mut start = 0_usize;
    let ends: Vec<usize> = projection
        .iter()
        .enumerate()
        .filter_map(|(position, &index)| {
            (tokens[index].token_type == TokenType::Comma).then_some(position)
        })
        .chain(std::iter::once(projection.len()))
        .collect();
    for end in ends {
        let item = &projection[start..end];
        start = end + 1;
        if item.is_empty()
            || item
                .iter()
                .any(|&index| tokens[index].token_type == TokenType::As)
            || simple_projection(tokens, item)
            || implicit_alias_projection(tokens, item)
        {
            continue;
        }
        spans.push(tokens[item[0]].span);
    }
    spans
}

fn simple_projection(tokens: &[Token], item: &[usize]) -> bool {
    let trimmed: Vec<usize> = item
        .iter()
        .copied()
        .skip_while(|&index| {
            matches!(
                tokens[index].token_type,
                TokenType::Distinct | TokenType::All
            )
        })
        .collect();
    trimmed.len() == 1
        && (is_identifier(&tokens[trimmed[0]]) || tokens[trimmed[0]].token_type == TokenType::Star)
        || trimmed.len() == QUALIFIED_REFERENCE_LENGTH
            && is_identifier(&tokens[trimmed[0]])
            && tokens[trimmed[1]].token_type == TokenType::Dot
            && (is_identifier(&tokens[trimmed[2]])
                || tokens[trimmed[2]].token_type == TokenType::Star)
}

fn implicit_alias_projection(tokens: &[Token], item: &[usize]) -> bool {
    item.len() >= IMPLICIT_ALIAS_MINIMUM_LENGTH
        && is_identifier(&tokens[*item.last().unwrap_or(&item[0])])
        && !matches!(
            tokens[item[item.len() - 2]].token_type,
            TokenType::Dot | TokenType::Plus | TokenType::Dash | TokenType::Star | TokenType::Slash
        )
}

fn unused_alias_spans(query: &QuerySlice<'_>) -> Vec<Span> {
    let QuerySlice {
        tokens,
        depths,
        direct: relation_clause,
        start: query_start,
        end: query_end,
        depth,
    } = query;
    let query_start = *query_start;
    let query_end = *query_end;
    let depth = *depth;
    let mut spans: Vec<Span> = Vec::new();
    for window in relation_clause.windows(2) {
        if tokens[window[0]].token_type != TokenType::As || !is_identifier(&tokens[window[1]]) {
            continue;
        }
        if significant_after(tokens, window[1])
            .is_some_and(|index| tokens[index].token_type == TokenType::LParen)
        {
            continue;
        }
        let alias = &tokens[window[1]].text;
        let used = (query_start..query_end).any(|index| {
            depths[index] >= depth
                && tokens[index].text.eq_ignore_ascii_case(alias)
                && significant_after(tokens, index)
                    .is_some_and(|next| tokens[next].token_type == TokenType::Dot)
        });
        if !used {
            spans.push(Span {
                start: tokens[window[0]].span.start,
                end: tokens[window[1]].span.end,
                line: tokens[window[0]].span.line,
                column: tokens[window[0]].span.column,
            });
        }
    }
    spans
}

fn null_rejected_left_join_spans(
    tokens: &[Token],
    direct: &[usize],
    relation_end: usize,
) -> Vec<Span> {
    let Some(where_position) = direct
        .iter()
        .position(|&index| tokens[index].token_type == TokenType::Where)
    else {
        return Vec::new();
    };
    if direct[where_position + 1..]
        .iter()
        .any(|&index| tokens[index].token_type == TokenType::Or)
    {
        return Vec::new();
    }
    let mut spans: Vec<Span> = Vec::new();
    for position in 0..relation_end {
        let index = direct[position];
        if tokens[index].token_type != TokenType::Left {
            continue;
        }
        let Some(join_position) = direct[position + 1..relation_end]
            .iter()
            .position(|&candidate| tokens[candidate].token_type == TokenType::Join)
            .map(|offset| position + 1 + offset)
        else {
            continue;
        };
        let Some(alias) = relation_alias_after_join(tokens, direct, join_position) else {
            continue;
        };
        if right_side_null_rejected(tokens, &direct[where_position + 1..], &alias) {
            spans.push(tokens[index].span);
        }
    }
    spans
}

fn right_side_null_rejected(tokens: &[Token], predicate: &[usize], alias: &str) -> bool {
    for window in predicate.windows(4) {
        if !tokens[window[0]].text.eq_ignore_ascii_case(alias)
            || tokens[window[1]].token_type != TokenType::Dot
            || !is_identifier(&tokens[window[2]])
        {
            continue;
        }
        if matches!(
            tokens[window[3]].token_type,
            TokenType::Eq
                | TokenType::Neq
                | TokenType::Lt
                | TokenType::Lte
                | TokenType::Gt
                | TokenType::Gte
                | TokenType::Like
                | TokenType::In
                | TokenType::Between
        ) {
            return true;
        }
    }
    for window in predicate.windows(6) {
        if tokens[window[0]].text.eq_ignore_ascii_case(alias)
            && tokens[window[1]].token_type == TokenType::Dot
            && is_identifier(&tokens[window[2]])
            && tokens[window[3]].token_type == TokenType::Is
            && tokens[window[4]].token_type == TokenType::Not
            && tokens[window[5]].token_type == TokenType::Null
        {
            return true;
        }
    }
    false
}

fn relation_alias_after_join(
    tokens: &[Token],
    direct: &[usize],
    join_position: usize,
) -> Option<String> {
    let table_position = join_position + 1;
    let table_index = *direct.get(table_position)?;
    let as_index = direct.get(table_position + 1).copied();
    let alias_index = direct.get(table_position + 2).copied();
    if as_index.is_some_and(|index| tokens[index].token_type == TokenType::As)
        && alias_index.is_some_and(|index| is_identifier(&tokens[index]))
    {
        return alias_index.map(|index| tokens[index].text.to_ascii_lowercase());
    }
    is_identifier(&tokens[table_index]).then(|| tokens[table_index].text.to_ascii_lowercase())
}

fn implicit_inner_join_spans(tokens: &[Token], relation_clause: &[usize]) -> Vec<Span> {
    let mut spans: Vec<Span> = Vec::new();
    for (position, &index) in relation_clause.iter().enumerate() {
        if is_plain_conditioned_join(tokens, relation_clause, position, index) {
            spans.push(tokens[index].span);
        }
    }
    spans
}

fn is_plain_conditioned_join(
    tokens: &[Token],
    relation_clause: &[usize],
    position: usize,
    index: usize,
) -> bool {
    if tokens[index].token_type != TokenType::Join
        || position > 0
            && matches!(
                tokens[relation_clause[position - 1]].token_type,
                TokenType::Inner
                    | TokenType::Left
                    | TokenType::Right
                    | TokenType::Full
                    | TokenType::Outer
                    | TokenType::Cross
                    | TokenType::Natural
                    | TokenType::AsOf
                    | TokenType::Semi
                    | TokenType::Anti
            )
    {
        return false;
    }
    for &candidate in &relation_clause[position + 1..] {
        if tokens[candidate].token_type == TokenType::Join {
            break;
        }
        if matches!(
            tokens[candidate].token_type,
            TokenType::On | TokenType::Using
        ) {
            return true;
        }
    }
    false
}

fn ambiguous_order_direction_spans(tokens: &[Token], direct: &[usize]) -> Vec<Span> {
    let mut spans: Vec<Span> = Vec::new();
    for (position, &index) in direct.iter().enumerate() {
        if tokens[index].token_type != TokenType::Order
            || direct
                .get(position + 1)
                .is_none_or(|&by| tokens[by].token_type != TokenType::By)
        {
            continue;
        }
        let end = direct[position + 2..]
            .iter()
            .position(|&candidate| is_clause_boundary(tokens[candidate].token_type))
            .map_or(direct.len(), |offset| position + 2 + offset);
        let clause = &direct[position + 2..end];
        let item_ends: Vec<usize> = clause
            .iter()
            .enumerate()
            .filter_map(|(item_position, &candidate)| {
                (tokens[candidate].token_type == TokenType::Comma).then_some(item_position)
            })
            .chain(std::iter::once(clause.len()))
            .collect();
        let mut item_start = 0_usize;
        let mut explicit = false;
        let mut implicit = false;
        for item_end in item_ends {
            let item = &clause[item_start..item_end];
            item_start = item_end + 1;
            let has_direction = item.last().is_some_and(|&candidate| {
                matches!(
                    tokens[candidate].token_type,
                    TokenType::Asc | TokenType::Desc
                )
            });
            explicit |= has_direction;
            implicit |= !has_direction && !item.is_empty();
        }
        if explicit && implicit {
            spans.push(tokens[index].span);
        }
    }
    spans
}

fn duplicate_alias_spans(tokens: &[Token], indices: &[usize]) -> Vec<Span> {
    let mut seen: HashSet<String> = HashSet::new();
    let mut duplicates: Vec<Span> = Vec::new();
    for window in indices.windows(2) {
        if tokens[window[0]].token_type != TokenType::As || !is_identifier(&tokens[window[1]]) {
            continue;
        }
        let normalized = tokens[window[1]].text.to_ascii_lowercase();
        if !seen.insert(normalized) {
            duplicates.push(tokens[window[1]].span);
        }
    }
    duplicates
}

fn mixed_reference_clause_spans(tokens: &[Token], direct: &[usize]) -> Vec<Span> {
    let mut spans: Vec<Span> = Vec::new();
    for (position, &index) in direct.iter().enumerate() {
        if !matches!(
            tokens[index].token_type,
            TokenType::Group | TokenType::Order
        ) || direct
            .get(position + 1)
            .is_none_or(|&by| tokens[by].token_type != TokenType::By)
        {
            continue;
        }
        let end = direct[position + 2..]
            .iter()
            .position(|&candidate| is_clause_boundary(tokens[candidate].token_type))
            .map_or(direct.len(), |offset| position + 2 + offset);
        let clause = &direct[position + 2..end];
        let mut has_number = false;
        let mut has_name = false;
        for (item_position, &candidate) in clause.iter().enumerate() {
            if item_position == 0
                || tokens[clause[item_position - 1]].token_type == TokenType::Comma
            {
                has_number |= tokens[candidate].token_type == TokenType::Number;
                has_name |= tokens[candidate].token_type != TokenType::Number;
            }
        }
        if has_number && has_name {
            spans.push(tokens[index].span);
        }
    }
    spans
}

fn is_clause_boundary(token_type: TokenType) -> bool {
    matches!(
        token_type,
        TokenType::Having
            | TokenType::Qualify
            | TokenType::Order
            | TokenType::Limit
            | TokenType::Offset
            | TokenType::Fetch
            | TokenType::Union
            | TokenType::Intersect
            | TokenType::Except
            | TokenType::Semicolon
    )
}

fn parenthesized_distinct_span(
    tokens: &[Token],
    depths: &[usize],
    open_index: usize,
) -> Option<Span> {
    let close_depth = depths[open_index] + 1;
    let close_index = (open_index + 1..tokens.len()).find(|&index| {
        tokens[index].token_type == TokenType::RParen && depths[index] == close_depth
    })?;
    Some(Span {
        start: tokens[significant_before(tokens, open_index)?].span.start,
        end: tokens[close_index].span.end,
        line: tokens[significant_before(tokens, open_index)?].span.line,
        column: tokens[significant_before(tokens, open_index)?].span.column,
    })
}

fn count_one_span(tokens: &[Token], significant: &[usize], position: usize) -> Option<Span> {
    let open = *significant.get(position + 1)?;
    let one = *significant.get(position + 2)?;
    let close = *significant.get(position + 3)?;
    (tokens[open].token_type == TokenType::LParen
        && tokens[one].token_type == TokenType::Number
        && tokens[one].text == COUNT_ONE_LITERAL
        && tokens[close].token_type == TokenType::RParen)
        .then_some(tokens[one].span)
}

fn simple_boolean_case_span(
    tokens: &[Token],
    significant: &[usize],
    position: usize,
) -> Option<Span> {
    let tail = &significant[position + 1..];
    let end_offset = tail
        .iter()
        .position(|&index| tokens[index].token_type == TokenType::End)?;
    let body = &tail[..=end_offset];
    if body
        .iter()
        .any(|&index| tokens[index].token_type == TokenType::Case)
    {
        return None;
    }
    let when_position = body
        .iter()
        .position(|&index| tokens[index].token_type == TokenType::When)?;
    let then_position = body
        .iter()
        .position(|&index| tokens[index].token_type == TokenType::Then)?;
    let else_position = body
        .iter()
        .position(|&index| tokens[index].token_type == TokenType::Else)?;
    let then_value = *body.get(then_position + 1)?;
    let else_value = *body.get(else_position + 1)?;
    if when_position != 0
        || tokens[then_value].token_type != TokenType::True
        || tokens[else_value].token_type != TokenType::False
        || else_position + 2 != body.len() - 1
    {
        return None;
    }
    let start = tokens[significant[position]].span;
    let end = tokens[*body.last()?].span;
    Some(Span {
        start: start.start,
        end: end.end,
        line: start.line,
        column: start.column,
    })
}

fn unstable_row_number_span(
    tokens: &[Token],
    depths: &[usize],
    function_index: usize,
) -> Option<Span> {
    let over_index = (function_index + 1..tokens.len()).find(|&index| {
        depths[index] == depths[function_index] && tokens[index].token_type == TokenType::Over
    })?;
    let open_index = significant_after(tokens, over_index)?;
    if tokens[open_index].token_type != TokenType::LParen {
        return None;
    }
    let close_depth = depths[open_index] + 1;
    let close_index = (open_index + 1..tokens.len()).find(|&index| {
        tokens[index].token_type == TokenType::RParen && depths[index] == close_depth
    })?;
    (!tokens[open_index + 1..close_index]
        .iter()
        .any(|token| matches!(token.token_type, TokenType::Order | TokenType::OrderBy)))
    .then_some(tokens[function_index].span)
}

fn null_not_in_span(
    tokens: &[Token],
    depths: &[usize],
    significant: &[usize],
    position: usize,
) -> Option<Span> {
    let in_index = *significant.get(position + 1)?;
    let open_index = *significant.get(position + 2)?;
    if tokens[in_index].token_type != TokenType::In
        || tokens[open_index].token_type != TokenType::LParen
    {
        return None;
    }
    let close_depth = depths[open_index] + 1;
    let close_index = (open_index + 1..tokens.len()).find(|&index| {
        tokens[index].token_type == TokenType::RParen && depths[index] == close_depth
    })?;
    let list_depth = depths[open_index] + 1;
    let list = &tokens[open_index + 1..close_index];
    (!list
        .iter()
        .any(|token| token.token_type == TokenType::Select)
        && list.iter().enumerate().any(|(offset, token)| {
            token.token_type == TokenType::Null && depths[open_index + 1 + offset] == list_depth
        }))
    .then_some(tokens[significant[position]].span)
}

fn constant_predicate(tokens: &[Token], indices: &[usize]) -> bool {
    let left = &tokens[indices[0]];
    let operator = &tokens[indices[1]];
    let right = &tokens[indices[2]];
    matches!(
        left.token_type,
        TokenType::Number | TokenType::String | TokenType::True | TokenType::False
    ) && left.token_type == right.token_type
        && left.text == right.text
        && matches!(operator.token_type, TokenType::Eq | TokenType::Neq)
}

fn set_arity_mismatch_spans(tokens: &[Token], depths: &[usize]) -> Vec<Span> {
    let mut spans: Vec<Span> = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        if !matches!(
            token.token_type,
            TokenType::Union | TokenType::Intersect | TokenType::Except
        ) {
            continue;
        }
        let depth = depths[index];
        let Some(left_select) = (0..index).rev().find(|&candidate| {
            depths[candidate] == depth && tokens[candidate].token_type == TokenType::Select
        }) else {
            continue;
        };
        let Some(right_select) = (index + 1..tokens.len()).find(|&candidate| {
            depths[candidate] == depth && tokens[candidate].token_type == TokenType::Select
        }) else {
            continue;
        };
        let left_query = QuerySlice {
            tokens,
            depths,
            direct: &[],
            start: left_select,
            end: index,
            depth,
        };
        let left_count = projection_arity(&left_query);
        let right_end = query_end(tokens, depths, right_select, depth);
        let right_query = QuerySlice {
            tokens,
            depths,
            direct: &[],
            start: right_select,
            end: right_end,
            depth,
        };
        let right_count = projection_arity(&right_query);
        if left_count
            .zip(right_count)
            .is_some_and(|(left, right)| left != right)
        {
            spans.push(token.span);
        }
    }
    spans
}

fn projection_arity(query: &QuerySlice<'_>) -> Option<usize> {
    let QuerySlice {
        tokens,
        depths,
        start: select,
        end,
        depth,
        ..
    } = query;
    let select = *select;
    let end = *end;
    let depth = *depth;
    let projection_end = (select + 1..end)
        .find(|&index| depths[index] == depth && tokens[index].token_type == TokenType::From)
        .unwrap_or(end);
    if (select + 1..projection_end)
        .any(|index| depths[index] == depth && tokens[index].token_type == TokenType::Star)
    {
        return None;
    }
    Some(
        1 + (select + 1..projection_end)
            .filter(|&index| depths[index] == depth && tokens[index].token_type == TokenType::Comma)
            .count(),
    )
}

fn is_identifier(token: &Token) -> bool {
    matches!(
        token.token_type,
        TokenType::Identifier | TokenType::QuotedIdentifier | TokenType::Var
    )
}
