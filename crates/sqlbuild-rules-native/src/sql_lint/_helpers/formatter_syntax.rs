use crate::sql_lint::_helpers::engine::token_depths;
use crate::sql_lint::constants::{
    CTE_MACRO_PLACEHOLDER_LITERAL, POSITION_ARGUMENT_SEPARATOR, POSTFIX_CAST_PREFIX_TOKEN_COUNT,
};
use polyglot_sql::Dialect;
use polyglot_sql::tokens::{Token, TokenType};
use std::collections::{HashMap, HashSet};

pub(super) struct ProtectedSql {
    pub sql: String,
    fragments: Vec<(String, String)>,
    in_functions: HashSet<String>,
}

impl ProtectedSql {
    pub(super) fn restore(&self, formatted: String, dialect: &Dialect) -> Result<String, String> {
        let tokens = dialect
            .tokenize(&formatted)
            .map_err(|error| error.to_string())?;
        let mut positions: HashMap<String, Vec<usize>> = HashMap::new();
        for (index, token) in tokens.iter().enumerate() {
            positions
                .entry(token.text.to_ascii_lowercase())
                .or_default()
                .push(index);
        }
        let mut edits: Vec<(usize, usize, String)> = Vec::new();
        for (placeholder, original) in &self.fragments {
            let key = placeholder
                .strip_suffix(" AS (SELECT 1)")
                .unwrap_or(placeholder)
                .trim_start_matches(':')
                .trim_start_matches('.')
                .trim_matches('\'')
                .to_ascii_lowercase();
            let found = positions
                .get(&key)
                .filter(|found| found.len() == 1)
                .ok_or_else(|| {
                    "native formatter could not restore a protected SQL fragment".to_string()
                })?;
            let index = found[0];
            if self.in_functions.contains(&key) {
                let mut depth = 0;
                let separator = (index + 1..tokens.len())
                    .find(|&position| {
                        match tokens[position].token_type {
                            TokenType::LParen => depth += 1,
                            TokenType::RParen => depth -= 1,
                            _ => {}
                        }
                        depth == 1 && tokens[position].token_type == TokenType::Comma
                    })
                    .ok_or_else(|| "native formatter lost a POSITION separator".to_string())?;
                edits.push((
                    tokens[separator].span.start,
                    tokens[separator].span.end,
                    " IN".to_string(),
                ));
            }
            if let Some(sentinel) = placeholder.strip_suffix(" AS (SELECT 1)") {
                let _ = sentinel;
                edits.push(restore_cte_macro(&tokens, index, original)?);
                continue;
            }
            if placeholder.starts_with("::") {
                edits.extend(restore_postfix_cast(&tokens, index, original)?);
                continue;
            }
            let start = if placeholder.starts_with('.') {
                if index == 0 || tokens[index - 1].token_type != TokenType::Dot {
                    return Err("native formatter changed a protected path accessor".to_string());
                }
                tokens[index - 1].span.start
            } else {
                tokens[index].span.start
            };
            edits.push((start, tokens[index].span.end, original.clone()));
        }
        edits.sort_by_key(|edit| edit.0);
        let chars: Vec<char> = formatted.chars().collect();
        let mut result = String::new();
        let mut cursor = 0;
        for (start, end, replacement) in edits {
            if start < cursor {
                return Err("native formatter produced overlapping syntax restorations".to_string());
            }
            result.extend(&chars[cursor..start]);
            result.push_str(&replacement);
            cursor = end;
        }
        result.extend(&chars[cursor..]);
        Ok(result)
    }
}

pub(super) fn protect_syntax(
    sql: &str,
    tokens: &[Token],
    cast_types: &[(usize, usize)],
    expressions: bool,
) -> Result<ProtectedSql, String> {
    let mut prefix = "__sqlbuild_format_".to_string();
    while sql.to_ascii_lowercase().contains(&prefix) {
        prefix.push('_');
    }
    let mut ranges: Vec<(usize, usize, String)> = Vec::new();
    let cte_macros = cte_macro_indices(tokens);
    let depths = token_depths(tokens);
    let mut separators: HashSet<usize> = HashSet::new();
    let mut in_functions: HashSet<String> = HashSet::new();
    let mut index = 0;
    while index < tokens.len() {
        let token = &tokens[index];
        let sentinel = format!("{prefix}{}__", ranges.len());
        if separators.contains(&index) {
            ranges.push((token.span.start, token.span.end, ",".to_string()));
            index += 1;
            continue;
        }
        let (end, replacement) = if cte_macros.contains(&index) {
            (index, format!("{sentinel} AS (SELECT 1)"))
        } else if !expressions {
            index += 1;
            continue;
        } else if let Some((_, end)) = cast_types.iter().find(|(start, _)| *start == index) {
            (*end, sentinel)
        } else if token.token_type == TokenType::DColon {
            (
                postfix_type_end(tokens, index + 1)?,
                format!("::{sentinel}"),
            )
        } else if token.token_type == TokenType::Colon
            && index > 0
            && tokens[index - 1].token_type != TokenType::String
            && tokens.get(index + 1).is_some_and(|next| {
                next.text
                    .chars()
                    .next()
                    .is_some_and(|character| character.is_alphanumeric() || character == '_')
                    || matches!(
                        next.token_type,
                        TokenType::QuotedIdentifier | TokenType::String
                    )
            })
        {
            (index + 1, format!(".{sentinel}"))
        } else if is_typed_literal(tokens, index) {
            (index + 1, sentinel)
        } else if matches!(token.token_type, TokenType::Var | TokenType::Identifier)
            && tokens.get(index + 1).is_some_and(|next| {
                matches!(next.token_type, TokenType::Var | TokenType::Identifier)
            })
            && tokens
                .get(index + 2)
                .is_some_and(|next| next.token_type == TokenType::Arrow)
        {
            (index + 1, sentinel)
        } else if matches!(token.text.to_ascii_uppercase().as_str(), "MOD" | "POSITION")
            && tokens
                .get(index + 1)
                .is_some_and(|next| next.token_type == TokenType::LParen)
        {
            if token.text.eq_ignore_ascii_case("POSITION") {
                let separator = (index + 2..tokens.len())
                    .take_while(|&position| {
                        !(tokens[position].token_type == TokenType::RParen
                            && depths[position] == depths[index] + 1)
                    })
                    .find(|&position| {
                        tokens[position].token_type == TokenType::In
                            && depths[position] == depths[index] + 1
                    });
                if let Some(separator) = separator {
                    separators.insert(separator);
                    in_functions.insert(sentinel.clone());
                }
            }
            (index, sentinel)
        } else if matches!(
            token.token_type,
            TokenType::String | TokenType::DollarString
        ) {
            (index, format!("'{sentinel}'"))
        } else {
            index += 1;
            continue;
        };
        ranges.push((token.span.start, tokens[end].span.end, replacement));
        index = end + 1;
    }
    let chars: Vec<char> = sql.chars().collect();
    let token_indices: HashMap<usize, usize> = tokens
        .iter()
        .enumerate()
        .map(|(index, token)| (token.span.start, index))
        .collect();
    let mut prepared = String::new();
    let mut fragments: Vec<(String, String)> = Vec::new();
    let mut cursor = 0;
    for (start, end, replacement) in ranges {
        prepared.extend(&chars[cursor..start]);
        prepared.push_str(&replacement);
        if replacement != POSITION_ARGUMENT_SEPARATOR {
            let first = token_indices[&start];
            let last = (first..tokens.len())
                .find(|&index| tokens[index].span.end == end)
                .ok_or_else(|| "native formatter lost a source fragment boundary".to_string())?;
            fragments.push((
                replacement,
                canonical_fragment(&chars, &tokens[first..=last]),
            ));
        }
        cursor = end;
    }
    prepared.extend(&chars[cursor..]);
    Ok(ProtectedSql {
        sql: prepared,
        fragments,
        in_functions,
    })
}

fn canonical_fragment(chars: &[char], tokens: &[Token]) -> String {
    let mut result = String::new();
    for (index, token) in tokens.iter().enumerate() {
        if index > 0
            && !matches!(
                token.token_type,
                TokenType::LParen
                    | TokenType::RParen
                    | TokenType::Comma
                    | TokenType::Dot
                    | TokenType::Colon
                    | TokenType::DColon
                    | TokenType::LBracket
                    | TokenType::RBracket
                    | TokenType::Lt
                    | TokenType::Gt
            )
            && !matches!(
                tokens[index - 1].token_type,
                TokenType::LParen
                    | TokenType::Dot
                    | TokenType::Colon
                    | TokenType::DColon
                    | TokenType::LBracket
                    | TokenType::Lt
            )
        {
            result.push(' ');
        }
        result.extend(&chars[token.span.start..token.span.end]);
    }
    result
}

fn cte_macro_indices(tokens: &[Token]) -> HashSet<usize> {
    let depths = token_depths(tokens);
    let mut scopes: HashSet<usize> = HashSet::new();
    let mut indices: HashSet<usize> = HashSet::new();
    for (index, token) in tokens.iter().enumerate() {
        if token.token_type == TokenType::With {
            scopes.insert(depths[index]);
        } else if token.token_type == TokenType::Select {
            scopes.remove(&depths[index]);
        } else if token.text.starts_with("__sqb_lint_")
            && scopes.contains(&depths[index])
            && index > 0
            && matches!(
                tokens[index - 1].token_type,
                TokenType::With | TokenType::Comma
            )
            && tokens
                .get(index + 1)
                .is_some_and(|next| matches!(next.token_type, TokenType::Comma | TokenType::Select))
        {
            indices.insert(index);
        }
    }
    indices
}

fn restore_cte_macro(
    tokens: &[Token],
    start: usize,
    original: &str,
) -> Result<(usize, usize, String), String> {
    let end = start + 5;
    if tokens
        .get(end)
        .is_none_or(|token| token.token_type != TokenType::RParen)
        || tokens[start + 1].token_type != TokenType::As
        || tokens[start + 2].token_type != TokenType::LParen
        || tokens[start + 3].token_type != TokenType::Select
        || tokens[start + 4].text != CTE_MACRO_PLACEHOLDER_LITERAL
    {
        return Err("native formatter changed a CTE macro placeholder".to_string());
    }
    Ok((
        tokens[start].span.start,
        tokens[end].span.end,
        original.to_string(),
    ))
}

fn restore_postfix_cast(
    tokens: &[Token],
    index: usize,
    original: &str,
) -> Result<Vec<(usize, usize, String)>, String> {
    if index < POSTFIX_CAST_PREFIX_TOKEN_COUNT
        || tokens[index - 1].token_type != TokenType::As
        || tokens
            .get(index + 1)
            .is_none_or(|token| token.token_type != TokenType::RParen)
    {
        return Err("native formatter changed a postfix cast wrapper".to_string());
    }
    let mut depth = 0;
    let mut open = None;
    for position in (0..index - 1).rev() {
        match tokens[position].token_type {
            TokenType::RParen => depth += 1,
            TokenType::LParen if depth == 0 => {
                open = Some(position);
                break;
            }
            TokenType::LParen => depth -= 1,
            _ => {}
        }
    }
    let open = open
        .filter(|&position| position > 0 && tokens[position - 1].token_type == TokenType::Cast)
        .ok_or_else(|| "native formatter could not identify a postfix cast wrapper".to_string())?;
    Ok(vec![
        (
            tokens[open - 1].span.start,
            tokens[open + 1].span.start,
            String::new(),
        ),
        (
            tokens[index - 2].span.end,
            tokens[index + 1].span.end,
            original.to_string(),
        ),
    ])
}

fn is_typed_literal(tokens: &[Token], index: usize) -> bool {
    matches!(
        tokens[index].text.to_ascii_uppercase().as_str(),
        "DATE"
            | "TIME"
            | "TIMESTAMP"
            | "TIMESTAMPTZ"
            | "TIMESTAMP_NTZ"
            | "TIMESTAMP_LTZ"
            | "TIMESTAMP_TZ"
    ) && tokens.get(index + 1).is_some_and(|token| {
        matches!(
            token.token_type,
            TokenType::String | TokenType::DollarString
        )
    })
}

fn postfix_type_end(tokens: &[Token], start: usize) -> Result<usize, String> {
    let Some(_) = tokens.get(start) else {
        return Err("native formatter could not locate a postfix cast type".to_string());
    };
    let mut end = start;
    while tokens.get(end + 1).is_some_and(|token| {
        matches!(
            token.text.to_ascii_uppercase().as_str(),
            "PRECISION" | "VARYING" | "WITH" | "WITHOUT" | "TIME" | "ZONE"
        )
    }) {
        end += 1;
    }
    if tokens
        .get(end + 1)
        .is_some_and(|token| token.token_type == TokenType::LParen)
    {
        let mut depth = 0;
        for (index, token) in tokens.iter().enumerate().skip(end + 1) {
            match token.token_type {
                TokenType::LParen => depth += 1,
                TokenType::RParen => {
                    depth -= 1;
                    if depth == 0 {
                        return Ok(index);
                    }
                }
                _ => {}
            }
        }
        return Err("native formatter could not locate postfix cast parameters".to_string());
    }
    Ok(end)
}
