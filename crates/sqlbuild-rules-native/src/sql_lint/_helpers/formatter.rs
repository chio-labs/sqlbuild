use std::collections::BTreeMap;
use std::str::FromStr;

use polyglot_sql::tokens::{Token, TokenType};
use polyglot_sql::{ComplexityGuardOptions, Dialect, DialectType, ParseOptions};
use rayon::iter::{IntoParallelIterator, ParallelIterator};

use crate::sql_lint::_helpers::formatter_syntax::{cte_macro_indices, protect_syntax};
use crate::sql_lint::constants::{
    CAST_TYPE_SEPARATOR_KEYWORD, CLOSE_PARENTHESIS, LINT_API_VERSION, OPEN_PARENTHESIS,
    VALUES_RELATION_PREFIX_TOKEN_COUNT,
};
use crate::sql_lint::models::{FormatRequest, FormatResponse};

const COMMENT_ATTACHMENT_FAILURE: &str =
    "native formatter could not preserve comment token attachments";
const TOKEN_PRESERVATION_FAILURE: &str =
    "native formatter would change authored SQL tokens, not only layout";
const UNSUPPORTED_SQL_FAILURE: &str =
    "native formatter could not safely restore literal or cast spelling";

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
    let original = request.sql.clone();
    match try_format_sql(request) {
        Ok(value) => Ok(value),
        Err(reason) => Ok(FormatResponse {
            version: LINT_API_VERSION,
            sql: original,
            changed: false,
            formatted: false,
            reason: Some(reason),
        }),
    }
}

fn try_format_sql(request: FormatRequest) -> Result<FormatResponse, String> {
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
    let parse_options = ParseOptions {
        complexity_guard: Some(ComplexityGuardOptions {
            max_function_call_depth: request.max_function_call_depth,
            ..Default::default()
        }),
    };
    let tokens = dialect
        .tokenize(&original)
        .map_err(|error| format!("native formatter tokenization failed: {error}"))?;
    let comments = comments_in(&original, &tokens);
    let neutral = neutralize_comments(&original, &comments);
    let validation_sql = protect_syntax(&neutral, &tokens, &[], false)?;
    dialect
        .parse_with_options(&validation_sql.sql, &parse_options)
        .map_err(|error| format!("native formatter could not parse SQL: {error}"))?;
    let semantic_tokens = without_statement_terminators(&tokens);
    let formatted_context = FormatOnceContext {
        parse_options: &parse_options,
        dialect: &dialect,
        original_sql: &neutral,
        original_tokens: &semantic_tokens,
        comments: &comments,
    };
    let formatted = preserve_authored_tokens(
        &neutral,
        format_once(&neutral, &formatted_context)?,
        &dialect,
    )?;
    let formatted_tokens = dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    let formatted_neutral =
        neutralize_comments(&formatted, &comments_in(&formatted, &formatted_tokens));
    let validation_sql = protect_syntax(&formatted_neutral, &formatted_tokens, &[], false)?;
    let _ = dialect
        .parse_with_options(&validation_sql.sql, &parse_options)
        .map_err(|error| error.to_string())?;
    let second_tokens = dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    let second_comments = comments_in(&formatted, &second_tokens);
    let second_neutral = neutralize_comments(&formatted, &second_comments);
    let second_semantic_tokens = without_statement_terminators(&second_tokens);
    let second_context = FormatOnceContext {
        parse_options: &parse_options,
        dialect: &dialect,
        original_sql: &second_neutral,
        original_tokens: &second_semantic_tokens,
        comments: &second_comments,
    };
    let second_pass = preserve_authored_tokens(
        &second_neutral,
        format_once(&second_neutral, &second_context)?,
        &dialect,
    )?;
    if second_pass != formatted {
        return Err("native formatter output is not idempotent".to_string());
    }
    let changed = formatted != original;
    response(formatted, changed, true, None)
}

/// Restores authored token text into generated layout, refusing any structural token change.
pub(crate) fn preserve_authored_tokens(
    authored_sql: &str,
    mut formatted: String,
    dialect: &Dialect,
) -> Result<String, String> {
    let authored = dialect
        .tokenize(authored_sql)
        .map_err(|error| error.to_string())?;
    let generated = dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    let mut replacements: Vec<(usize, usize, String)> = Vec::new();
    let mut authored_index = 0;
    let mut generated_index = 0;
    while authored_index < authored.len() || generated_index < generated.len() {
        let before = authored.get(authored_index);
        let after = generated.get(generated_index);
        match (before, after) {
            (before, Some(after))
                if after.token_type == TokenType::As
                    && before.is_none_or(|token| token.token_type != TokenType::As) =>
            {
                generated_index += 1;
            }
            (Some(before), Some(after)) if tokens_align(before, after) => {
                let authored_text = raw_token_text(authored_sql, before)?;
                let generated_text = raw_token_text(&formatted, after)?;
                if authored_text != generated_text
                    && !(is_unquoted_word(&authored_text)
                        && authored_text.eq_ignore_ascii_case(&generated_text))
                {
                    replacements.push((after.span.start, after.span.end, authored_text));
                }
                authored_index += 1;
                generated_index += 1;
            }
            (Some(before), after) if is_optional_terminator(&authored, authored_index, before) => {
                if after.is_some_and(|token| token.token_type == before.token_type) {
                    generated_index += 1;
                }
                authored_index += 1;
            }
            (None, Some(after)) if after.token_type == TokenType::Semicolon => {
                generated_index += 1;
            }
            _ => return Err(TOKEN_PRESERVATION_FAILURE.to_string()),
        }
    }
    for (start, end, text) in replacements.into_iter().rev() {
        let start = char_to_byte(&formatted, start)?;
        let end = char_to_byte(&formatted, end)?;
        formatted.replace_range(start..end, &text);
    }
    Ok(formatted)
}

fn tokens_align(before: &Token, after: &Token) -> bool {
    before.token_type == after.token_type || (is_word_token(before) && is_word_token(after))
}

fn is_word_token(token: &Token) -> bool {
    is_unquoted_word(&token.text)
}

fn is_unquoted_word(text: &str) -> bool {
    let mut characters = text.chars();
    characters
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
        && characters
            .all(|character| character.is_ascii_alphanumeric() || matches!(character, '_' | '$'))
}

fn is_optional_terminator(tokens: &[Token], index: usize, token: &Token) -> bool {
    token.token_type == TokenType::Semicolon
        || (token.token_type == TokenType::Comma
            && tokens
                .get(index + 1)
                .is_some_and(|next| next.token_type == TokenType::From))
}

fn raw_token_text(sql: &str, token: &Token) -> Result<String, String> {
    char_slice(sql, token.span.start, token.span.end)
        .ok_or_else(|| TOKEN_PRESERVATION_FAILURE.to_string())
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
    parse_options: &'a ParseOptions,
    dialect: &'a Dialect,
    original_sql: &'a str,
    original_tokens: &'a [Token],
    comments: &'a [Comment],
}

fn format_once(neutral_sql: &str, context: &FormatOnceContext<'_>) -> Result<String, String> {
    let protected = protect_syntax(
        neutral_sql,
        context.original_tokens,
        &cast_type_token_ranges(context)?,
        true,
    )?;
    let expressions = context
        .dialect
        .parse_with_options(&protected.sql, context.parse_options)
        .map_err(|error| error.to_string())?;
    let formatted_statements: Result<Vec<String>, String> = expressions
        .iter()
        .map(|expression| {
            context
                .dialect
                .generate_pretty(expression)
                .map_err(|error| error.to_string())
        })
        .collect();
    let mut formatted = protected.restore(formatted_statements?.join(";\n"), context.dialect)?;
    formatted = restore_unparenthesized_from_values(formatted, context)?;
    formatted = restore_null_treatment(formatted, context)?;
    formatted = layout_cte_macros(formatted, context)?;
    if context.comments.is_empty() {
        return Ok(formatted);
    }
    formatted = restore_implicit_aliases(formatted, context)?;
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
    let mut insertions: Vec<CommentInsertion> = Vec::new();
    let mut leading_groups: BTreeMap<usize, Vec<&Comment>> = BTreeMap::new();
    for comment in context.comments {
        if let Some(target) = leading_comment_target(context, comment) {
            leading_groups.entry(target).or_default().push(comment);
        } else {
            insertions.push(trailing_comment_insertion(
                &formatted,
                &formatted_tokens,
                context,
                comment,
            ));
        }
    }
    for (target, comments) in &leading_groups {
        insertions.push(leading_comment_insertion(
            &formatted,
            &formatted_tokens[*target],
            comments,
        ));
    }
    insertions.sort_by_key(|insertion| insertion.start);
    for insertion in insertions.into_iter().rev() {
        let start = char_to_byte(&formatted, insertion.start)?;
        let end = char_to_byte(&formatted, insertion.end)?;
        formatted.replace_range(start..end, &insertion.text);
    }
    Ok(formatted)
}

fn restore_implicit_aliases(
    mut formatted: String,
    context: &FormatOnceContext<'_>,
) -> Result<String, String> {
    let tokens = context
        .dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    let mut original = context.original_tokens.iter().peekable();
    let mut removals: Vec<(usize, usize)> = Vec::new();
    for token in &tokens {
        if original
            .peek()
            .is_some_and(|before| before.token_type == token.token_type)
        {
            original.next();
        } else if token.token_type == TokenType::As {
            removals.push((token.span.start, token.span.end));
        } else {
            return Err(format!(
                "{COMMENT_ATTACHMENT_FAILURE}: expected {:?}, generated {:?}",
                original.peek().map(|token| token.token_type),
                token.token_type
            ));
        }
    }
    if original.next().is_some() {
        return Err(COMMENT_ATTACHMENT_FAILURE.to_string());
    }
    for (start, end) in removals.into_iter().rev() {
        let start = char_to_byte(&formatted, start)?;
        let end = char_to_byte(&formatted, end)?;
        formatted.replace_range(
            start..end + usize::from(formatted[end..].starts_with(' ')),
            "",
        );
    }
    Ok(formatted)
}

fn layout_cte_macros(
    mut formatted: String,
    context: &FormatOnceContext<'_>,
) -> Result<String, String> {
    let tokens = context
        .dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    let macros = cte_macro_indices(&tokens);
    if macros.is_empty() {
        return Ok(formatted);
    }
    let depths = crate::sql_lint::_helpers::engine::token_depths(&tokens);
    let chars: Vec<char> = formatted.chars().collect();
    let mut gaps: BTreeMap<(usize, usize), String> = BTreeMap::new();
    for index in macros {
        let with = (0..index)
            .rev()
            .find(|&previous| {
                tokens[previous].token_type == TokenType::With && depths[previous] == depths[index]
            })
            .ok_or_else(|| "native formatter lost a CTE macro scope".to_string())?;
        let indentation = line_indentation(&chars, tokens[with].span.start);
        let newline = format!("\n{}", " ".repeat(indentation));
        gaps.insert(
            (tokens[index - 1].span.end, tokens[index].span.start),
            newline.clone(),
        );
        if tokens
            .get(index + 1)
            .is_some_and(|token| token.token_type == TokenType::Comma)
            && let Some(next) = tokens.get(index + 2)
        {
            gaps.insert((tokens[index + 1].span.end, next.span.start), newline);
        }
    }
    for ((start, end), replacement) in gaps.into_iter().rev() {
        let start = char_to_byte(&formatted, start)?;
        let end = char_to_byte(&formatted, end)?;
        formatted.replace_range(start..end, &replacement);
    }
    Ok(formatted)
}

fn restore_null_treatment(
    mut formatted: String,
    context: &FormatOnceContext<'_>,
) -> Result<String, String> {
    let authored: Vec<bool> = context
        .original_tokens
        .windows(3)
        .filter(|tokens| {
            matches!(
                tokens[0].text.to_ascii_uppercase().as_str(),
                "IGNORE" | "RESPECT"
            ) && tokens[1].text.eq_ignore_ascii_case("NULLS")
        })
        .map(|tokens| tokens[2].token_type == TokenType::RParen)
        .collect();
    if authored.is_empty() {
        return Ok(formatted);
    }
    let tokens = context
        .dialect
        .tokenize(&formatted)
        .map_err(|error| error.to_string())?;
    let generated: Vec<usize> = (1..tokens.len().saturating_sub(1))
        .filter(|&index| {
            matches!(
                tokens[index].text.to_ascii_uppercase().as_str(),
                "IGNORE" | "RESPECT"
            ) && tokens[index + 1].text.eq_ignore_ascii_case("NULLS")
        })
        .collect();
    if authored.len() != generated.len() {
        return Err("native formatter changed null-treatment clauses".to_string());
    }
    for (inside, index) in authored.into_iter().zip(generated).rev() {
        if inside && tokens[index - 1].token_type == TokenType::RParen {
            let start = char_to_byte(&formatted, tokens[index - 1].span.start)?;
            let end = char_to_byte(&formatted, tokens[index + 1].span.end)?;
            formatted.replace_range(
                start..end,
                &format!(" {} NULLS)", tokens[index].text.to_ascii_uppercase()),
            );
        }
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
        return Err("native formatter could not preserve VALUES relation count".to_string());
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
            return Err("native formatter could not locate the VALUES wrapper end".to_string());
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

struct CommentInsertion {
    start: usize,
    end: usize,
    text: String,
}

fn leading_comment_target(context: &FormatOnceContext<'_>, comment: &Comment) -> Option<usize> {
    if !comment.leading {
        return None;
    }
    context
        .original_tokens
        .iter()
        .position(|token| token.span.start >= comment.end)
}

/// Place a block of leading comments on their own lines directly above the token they explain.
fn leading_comment_insertion(
    formatted: &str,
    target: &Token,
    comments: &[&Comment],
) -> CommentInsertion {
    let characters: Vec<char> = formatted.chars().collect();
    let target_start = target.span.start.min(characters.len());
    let mut whitespace_start = target_start;
    while whitespace_start > 0
        && characters[whitespace_start - 1].is_whitespace()
        && characters[whitespace_start - 1] != '\n'
    {
        whitespace_start -= 1;
    }
    let at_line_start = whitespace_start == 0 || characters[whitespace_start - 1] == '\n';
    if at_line_start {
        let indentation = " ".repeat(target_start - whitespace_start);
        let text: String = comments
            .iter()
            .map(|comment| format!("{}\n{indentation}", comment.text))
            .collect();
        return CommentInsertion {
            start: target_start,
            end: target_start,
            text,
        };
    }
    let indentation = " ".repeat(line_indentation(&characters, whitespace_start));
    let text: String = comments
        .iter()
        .map(|comment| format!("\n{indentation}{}", comment.text))
        .chain(std::iter::once(format!("\n{indentation}")))
        .collect();
    CommentInsertion {
        start: whitespace_start,
        end: target_start,
        text,
    }
}

fn line_indentation(characters: &[char], offset: usize) -> usize {
    let line_start = characters[..offset]
        .iter()
        .rposition(|character| *character == '\n')
        .map_or(0, |position| position + 1);
    characters[line_start..offset]
        .iter()
        .take_while(|character| **character == ' ' || **character == '\t')
        .count()
}

fn trailing_comment_insertion(
    formatted: &str,
    formatted_tokens: &[Token],
    context: &FormatOnceContext<'_>,
    comment: &Comment,
) -> CommentInsertion {
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
    CommentInsertion {
        start: char_offset,
        end: char_offset,
        text: format!("{separator}{}{terminator}", comment.text),
    }
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
        .enumerate()
        .filter(|(index, token)| {
            token.token_type != TokenType::Semicolon
                && !(token.token_type == TokenType::Comma
                    && tokens
                        .get(index + 1)
                        .is_some_and(|next| next.token_type == TokenType::From))
        })
        .map(|(_, token)| token.clone())
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
        reason: reason.map(str::to_owned),
    })
}
