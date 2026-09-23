use std::str::FromStr;

use polyglot_sql::tokens::Token;
use polyglot_sql::{Dialect, DialectType, format_by_name};
use rayon::iter::{IntoParallelIterator, ParallelIterator};

use crate::sql_lint::constants::{
    CAST_TYPE_SEPARATOR_KEYWORD, CLOSE_PARENTHESIS, LINT_API_VERSION, OPEN_PARENTHESIS,
    VALUES_RELATION_PREFIX_TOKEN_COUNT,
};
use crate::sql_lint::models::{FormatRequest, FormatResponse};

const COMMENT_ATTACHMENT_FAILURE: &str =
    "native formatter could not preserve comment token attachments";
const UNSUPPORTED_SQL_FAILURE: &str = "native formatter could not safely format unsupported SQL";

pub(crate) fn format_json_impl(request_json: &str) -> Result<String, String> {
    let request: FormatRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let response = format_sql(request)?;
    serde_json::to_string(&response).map_err(|error| error.to_string())
}

pub(crate) fn format_batch_json_impl(request_json: &str) -> Result<String, String> {
    let requests: Vec<FormatRequest> =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let responses: Result<Vec<FormatResponse>, String> =
        requests.into_par_iter().map(format_sql).collect();
    serde_json::to_string(&responses?).map_err(|error| error.to_string())
}

fn format_sql(request: FormatRequest) -> Result<FormatResponse, String> {
    if request.version != LINT_API_VERSION {
        return Err(format!(
            "unsupported native format request version {}; expected {LINT_API_VERSION}",
            request.version
        ));
    }
    let original = request.sql;
    let dialect_type =
        DialectType::from_str(&request.dialect).map_err(|error| error.to_string())?;
    let dialect = Dialect::get(dialect_type);
    let tokens = match dialect.tokenize(&original) {
        Ok(value) => value,
        Err(_) => return response(original, false, false, Some(UNSUPPORTED_SQL_FAILURE)),
    };
    let comments = comments_in(&original, &tokens);
    let neutral = neutralize_comments(&original, &comments);
    if dialect.parse(&neutral).is_err() {
        return response(original, false, false, Some(UNSUPPORTED_SQL_FAILURE));
    }
    let semantic_tokens = without_statement_terminators(&tokens);
    let formatted_context = FormatOnceContext {
        dialect_name: &request.dialect,
        dialect: &dialect,
        original_sql: &neutral,
        original_tokens: &semantic_tokens,
        comments: &comments,
    };
    let formatted = match format_once(&neutral, &formatted_context) {
        Ok(value) => value,
        Err(error) if error == COMMENT_ATTACHMENT_FAILURE => {
            return response(original, false, false, Some(COMMENT_ATTACHMENT_FAILURE));
        }
        Err(_) => return response(original, false, false, Some(UNSUPPORTED_SQL_FAILURE)),
    };
    let formatted_tokens = dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    let formatted_neutral =
        neutralize_comments(&formatted, &comments_in(&formatted, &formatted_tokens));
    let _ = dialect
        .parse(&formatted_neutral)
        .map_err(|error| error.to_string())?;
    let second_tokens = dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    let second_comments = comments_in(&formatted, &second_tokens);
    let second_neutral = neutralize_comments(&formatted, &second_comments);
    let second_semantic_tokens = without_statement_terminators(&second_tokens);
    let second_context = FormatOnceContext {
        dialect_name: &request.dialect,
        dialect: &dialect,
        original_sql: &second_neutral,
        original_tokens: &second_semantic_tokens,
        comments: &second_comments,
    };
    let second_pass = match format_once(&second_neutral, &second_context) {
        Ok(value) => value,
        Err(error) if error == COMMENT_ATTACHMENT_FAILURE => {
            return response(original, false, false, Some(COMMENT_ATTACHMENT_FAILURE));
        }
        Err(error) => return Err(error),
    };
    if second_pass != formatted {
        return Err("native formatter output is not idempotent".to_string());
    }
    let changed = formatted != original;
    response(formatted, changed, true, None)
}

#[derive(Debug, Clone)]
struct Comment {
    start: usize,
    end: usize,
    text: String,
    line: bool,
    leading: bool,
}

struct FormatOnceContext<'a> {
    dialect_name: &'a str,
    dialect: &'a Dialect,
    original_sql: &'a str,
    original_tokens: &'a [Token],
    comments: &'a [Comment],
}

fn format_once(neutral_sql: &str, context: &FormatOnceContext<'_>) -> Result<String, String> {
    let mut formatted = format_by_name(neutral_sql, context.dialect_name)
        .map_err(|error| error.to_string())?
        .join(";\n");
    formatted = restore_unparenthesized_from_values(formatted, context)?;
    formatted = restore_string_literals(formatted, context)?;
    formatted = restore_cast_type_spellings(formatted, context)?;
    if context.comments.is_empty() {
        return Ok(formatted);
    }
    let formatted_tokens = context
        .dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    if context.original_tokens.len() != formatted_tokens.len()
        || context
            .original_tokens
            .iter()
            .zip(&formatted_tokens)
            .any(|(before, after)| before.token_type != after.token_type)
    {
        return Err(COMMENT_ATTACHMENT_FAILURE.to_string());
    }
    let mut insertions: Vec<(usize, String)> = Vec::new();
    for comment in context.comments {
        insertions.push(comment_insertion(
            &formatted,
            &formatted_tokens,
            context,
            comment,
        ));
    }
    insertions.sort_by_key(|(offset, _)| *offset);
    for (char_offset, text) in insertions.into_iter().rev() {
        formatted.insert_str(char_to_byte(&formatted, char_offset)?, &text);
    }
    Ok(formatted)
}

fn restore_unparenthesized_from_values(
    mut formatted: String,
    context: &FormatOnceContext<'_>,
) -> Result<String, String> {
    let authored_parenthesized: Vec<bool> = context
        .original_tokens
        .iter()
        .enumerate()
        .filter(|(_, token)| token_text(context.original_sql, token).as_deref() == Some("VALUES"))
        .map(|(index, _)| {
            index > 0
                && token_text(context.original_sql, &context.original_tokens[index - 1]).as_deref()
                    == Some(OPEN_PARENTHESIS)
        })
        .collect();
    if authored_parenthesized.is_empty() {
        return Ok(formatted);
    }
    let formatted_tokens = context
        .dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    let formatted_values: Vec<usize> = formatted_tokens
        .iter()
        .enumerate()
        .filter_map(|(index, token)| {
            (token_text(&formatted, token).as_deref() == Some("VALUES")).then_some(index)
        })
        .collect();
    if authored_parenthesized.len() != formatted_values.len() {
        return Ok(formatted);
    }
    let mut removals: Vec<(usize, usize)> = Vec::new();
    for (was_parenthesized, values_index) in
        authored_parenthesized.into_iter().zip(formatted_values)
    {
        if was_parenthesized || values_index < VALUES_RELATION_PREFIX_TOKEN_COUNT {
            continue;
        }
        let wrapper_index = values_index - 1;
        let relation_index = values_index - 2;
        let relation_keyword = token_text(&formatted, &formatted_tokens[relation_index]);
        if token_text(&formatted, &formatted_tokens[wrapper_index]).as_deref()
            != Some(OPEN_PARENTHESIS)
            || !matches!(relation_keyword.as_deref(), Some("FROM" | "JOIN"))
        {
            continue;
        }
        let mut depth = 0_i32;
        let mut close_index: Option<usize> = None;
        for (index, token) in formatted_tokens.iter().enumerate().skip(wrapper_index) {
            match token_text(&formatted, token).as_deref() {
                Some(OPEN_PARENTHESIS) => depth += 1,
                Some(CLOSE_PARENTHESIS) => {
                    depth -= 1;
                    if depth == 0 {
                        close_index = Some(index);
                        break;
                    }
                }
                _ => {}
            }
        }
        let Some(close_index) = close_index else {
            return Ok(formatted);
        };
        let open = &formatted_tokens[wrapper_index];
        let close = &formatted_tokens[close_index];
        removals.push((open.span.start, open.span.end));
        removals.push((close.span.start, close.span.end));
    }
    removals.sort_unstable();
    for (start, end) in removals.into_iter().rev() {
        let start = char_to_byte(&formatted, start)?;
        let end = char_to_byte(&formatted, end)?;
        formatted.replace_range(start..end, "");
    }
    Ok(formatted)
}

fn token_text(sql: &str, token: &Token) -> Option<String> {
    char_slice(sql, token.span.start, token.span.end).map(|value| value.to_ascii_uppercase())
}

fn comment_insertion(
    formatted: &str,
    formatted_tokens: &[Token],
    context: &FormatOnceContext<'_>,
    comment: &Comment,
) -> (usize, String) {
    if comment.leading
        && let Some(next) = context
            .original_tokens
            .iter()
            .position(|token| token.span.start >= comment.end)
    {
        let target = &formatted_tokens[next];
        let indentation = indentation_before(formatted, target.span.start);
        return (
            target.span.start,
            format!("{}\n{}", comment.text, " ".repeat(indentation)),
        );
    }
    let previous = context
        .original_tokens
        .iter()
        .rposition(|token| token.span.end <= comment.start);
    let char_offset = previous.map_or(0, |index| formatted_tokens[index].span.end);
    let separator = if char_offset == 0 { "" } else { " " };
    let followed_by_newline = formatted.chars().nth(char_offset) == Some('\n');
    let terminator = if (comment.line || char_offset == 0) && !followed_by_newline {
        "\n"
    } else {
        ""
    };
    (
        char_offset,
        format!("{separator}{}{terminator}", comment.text),
    )
}

fn indentation_before(value: &str, char_offset: usize) -> usize {
    let characters: Vec<char> = value.chars().collect();
    let mut index = char_offset.min(characters.len());
    let mut indentation = 0_usize;
    while index > 0 {
        index -= 1;
        if characters[index] == '\n' {
            break;
        }
        if characters[index].is_whitespace() {
            indentation += 1;
        }
    }
    indentation
}

fn restore_string_literals(
    mut formatted: String,
    context: &FormatOnceContext<'_>,
) -> Result<String, String> {
    let originals: Vec<String> = context
        .original_tokens
        .iter()
        .filter(|token| token.token_type == polyglot_sql::tokens::TokenType::String)
        .map(|token| char_slice(context.original_sql, token.span.start, token.span.end))
        .collect::<Option<Vec<String>>>()
        .ok_or_else(|| UNSUPPORTED_SQL_FAILURE.to_string())?;
    let formatted_tokens = context
        .dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    let formatted_strings: Vec<&Token> = formatted_tokens
        .iter()
        .filter(|token| token.token_type == polyglot_sql::tokens::TokenType::String)
        .collect();
    if originals.len() != formatted_strings.len() {
        return Err(UNSUPPORTED_SQL_FAILURE.to_string());
    }
    for (token, original) in formatted_strings.into_iter().zip(originals).rev() {
        let start = char_to_byte(&formatted, token.span.start)?;
        let end = char_to_byte(&formatted, token.span.end)?;
        formatted.replace_range(start..end, &original);
    }
    Ok(formatted)
}

fn restore_cast_type_spellings(
    mut formatted: String,
    context: &FormatOnceContext<'_>,
) -> Result<String, String> {
    let type_ranges = cast_type_token_ranges(context)?;
    if type_ranges.is_empty() {
        return Ok(formatted);
    }
    let formatted_tokens = context
        .dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    if context.original_tokens.len() != formatted_tokens.len() {
        return Err(UNSUPPORTED_SQL_FAILURE.to_string());
    }
    let mut type_indices: Vec<usize> = type_ranges
        .into_iter()
        .flat_map(|(start, end)| start..=end)
        .collect();
    type_indices.sort_unstable();
    type_indices.dedup();
    for index in type_indices.into_iter().rev() {
        let original_token = &context.original_tokens[index];
        let formatted_token = &formatted_tokens[index];
        let original = char_slice(
            context.original_sql,
            original_token.span.start,
            original_token.span.end,
        )
        .ok_or_else(|| UNSUPPORTED_SQL_FAILURE.to_string())?;
        let start = char_to_byte(&formatted, formatted_token.span.start)?;
        let end = char_to_byte(&formatted, formatted_token.span.end)?;
        formatted.replace_range(start..end, &original);
    }
    Ok(formatted)
}

fn cast_type_token_ranges(context: &FormatOnceContext<'_>) -> Result<Vec<(usize, usize)>, String> {
    let mut ranges: Vec<(usize, usize)> = Vec::new();
    let mut cast_type_starts: Vec<Option<usize>> = Vec::new();
    let mut previous: Option<String> = None;
    for (index, token) in context.original_tokens.iter().enumerate() {
        let text = char_slice(context.original_sql, token.span.start, token.span.end)
            .ok_or_else(|| UNSUPPORTED_SQL_FAILURE.to_string())?;
        let normalized = text.to_ascii_uppercase();
        if normalized == OPEN_PARENTHESIS {
            let opens_cast = previous
                .as_deref()
                .is_some_and(|value| matches!(value, "CAST" | "TRY_CAST"));
            cast_type_starts.push(opens_cast.then_some(usize::MAX));
        } else if normalized == CLOSE_PARENTHESIS {
            if let Some(Some(type_start)) = cast_type_starts.pop()
                && type_start != usize::MAX
                && type_start < index
            {
                ranges.push((type_start, index - 1));
            }
        } else if normalized == CAST_TYPE_SEPARATOR_KEYWORD
            && let Some(Some(type_start)) = cast_type_starts.last_mut()
            && *type_start == usize::MAX
        {
            *type_start = index + 1;
        }
        previous = Some(normalized);
    }
    ranges.sort_unstable();
    Ok(ranges)
}

fn char_slice(value: &str, start: usize, end: usize) -> Option<String> {
    (start <= end).then(|| value.chars().skip(start).take(end - start).collect())
}

fn without_statement_terminators(tokens: &[Token]) -> Vec<Token> {
    tokens
        .iter()
        .filter(|token| token.token_type != polyglot_sql::tokens::TokenType::Semicolon)
        .cloned()
        .collect()
}

fn comments_in(sql: &str, tokens: &[Token]) -> Vec<Comment> {
    let characters: Vec<char> = sql.chars().collect();
    let mut comments: Vec<Comment> = Vec::new();
    let mut gap_start = 0_usize;
    for token in tokens {
        comments.extend(comments_in_gap(&characters, gap_start, token.span.start));
        gap_start = token.span.end;
    }
    comments.extend(comments_in_gap(&characters, gap_start, characters.len()));
    comments
}

fn comments_in_gap(characters: &[char], start: usize, end: usize) -> Vec<Comment> {
    let mut comments: Vec<Comment> = Vec::new();
    let mut index = start;
    while index < end {
        let line = characters[index] == '-' && characters.get(index + 1) == Some(&'-');
        let block = characters[index] == '/' && characters.get(index + 1) == Some(&'*');
        if !line && !block {
            index += 1;
            continue;
        }
        let start = index;
        let line_start = (0..start)
            .rev()
            .find(|&position| characters[position] == '\n')
            .map_or(0, |position| position + 1);
        let leading = characters[line_start..start]
            .iter()
            .all(|character| character.is_whitespace());
        index += 2;
        if line {
            while index < end && characters[index] != '\n' {
                index += 1;
            }
        } else {
            while index + 1 < end && !(characters[index] == '*' && characters[index + 1] == '/') {
                index += 1;
            }
            index = (index + 2).min(end);
        }
        comments.push(Comment {
            start,
            end: index,
            text: characters[start..index].iter().collect(),
            line,
            leading,
        });
    }
    comments
}

fn neutralize_comments(sql: &str, comments: &[Comment]) -> String {
    let mut characters: Vec<char> = sql.chars().collect();
    for comment in comments {
        for character in &mut characters[comment.start..comment.end] {
            if *character != '\n' && *character != '\r' {
                *character = ' ';
            }
        }
    }
    characters.into_iter().collect()
}

fn char_to_byte(value: &str, char_offset: usize) -> Result<usize, String> {
    if char_offset == value.chars().count() {
        return Ok(value.len());
    }
    value
        .char_indices()
        .nth(char_offset)
        .map(|(offset, _)| offset)
        .ok_or_else(|| "native formatter produced an invalid character offset".to_string())
}

fn response(
    sql: String,
    changed: bool,
    formatted: bool,
    reason: Option<&'static str>,
) -> Result<FormatResponse, String> {
    Ok(FormatResponse {
        version: LINT_API_VERSION,
        changed,
        sql,
        formatted,
        reason,
    })
}
