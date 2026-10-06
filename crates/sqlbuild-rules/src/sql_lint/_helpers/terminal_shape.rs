use polyglot_sql::tokens::{Span, Token, TokenType};

const CEREMONIAL_SELECT_LITERAL: &str = "1";

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
