use std::collections::{BTreeMap, HashMap};
use std::str::FromStr;

use polyglot_sql::tokens::{Token, TokenType};
use polyglot_sql::{ComplexityGuardOptions, Dialect, DialectType, ParseOptions};
use rayon::iter::{IntoParallelIterator, ParallelIterator};

use crate::sql_lint::_helpers::formatter_syntax::{cte_macro_indices, protect_syntax};
use crate::sql_lint::_helpers::printed_layout::{PrintedSql, WrapOptions, wrap_lines};
use crate::sql_lint::_helpers::token_layout::{
    AuthoredSql, KeywordRecase, comments_in, neutralize_comments, print_authored_tokens,
    verify_token_invariant,
};
use crate::sql_lint::constants::{
    CAST_TYPE_SEPARATOR_KEYWORD, CLOSE_PARENTHESIS, LINT_API_VERSION, OPEN_PARENTHESIS,
};
use crate::sql_lint::models::{FormatRequest, FormatResponse};

const NOT_IDEMPOTENT_FAILURE: &str = "native formatter output is not idempotent";
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
    let wrap = request.line_width.map(|line_width| WrapOptions {
        line_width,
        token_widths: &request.token_widths,
    });
    let layout = Layout {
        dialect: &dialect,
        wrap: wrap.as_ref(),
    };
    let (formatted, oracle) = format_layout(&original, &layout, &parse_options)?;
    if relayout(&formatted, &oracle, &layout)? != formatted {
        return Err(NOT_IDEMPOTENT_FAILURE.to_string());
    }
    let changed = formatted != original;
    Ok(FormatResponse {
        version: LINT_API_VERSION,
        changed,
        sql: formatted,
        formatted: true,
        reason: None,
    })
}

/// Print the tokens of `sql` with parse-tree whitespace; return the output and its oracle.
fn format_layout(
    sql: &str,
    layout: &Layout<'_>,
    parse_options: &ParseOptions,
) -> Result<(String, String), String> {
    let dialect = layout.dialect;
    let tokens = dialect
        .tokenize(sql)
        .map_err(|error| format!("native formatter tokenization failed: {error}"))?;
    if tokens.is_empty() {
        return Ok((sql.to_string(), sql.to_string()));
    }
    let comments = comments_in(sql, &tokens);
    let neutral = neutralize_comments(sql, &comments);
    let validation_sql = protect_syntax(&neutral, &tokens, &[], false)?;
    dialect
        .parse_with_options(&validation_sql.sql, parse_options)
        .map_err(|error| format!("native formatter could not parse SQL: {error}"))?;
    let semantic_tokens = without_statement_terminators(&tokens);
    let oracle = layout_oracle(&neutral, &semantic_tokens, dialect, parse_options)?;
    let authored = AuthoredSql {
        sql,
        tokens: &tokens,
        comments: &comments,
    };
    let (printed, recases) = layout.print(&authored, &oracle)?;
    verify_token_invariant(sql, &printed, dialect, &recases)?;
    Ok((printed, oracle))
}

/// Re-print formatted SQL against its oracle; unchanged tokens imply an unchanged layout.
fn relayout(formatted: &str, oracle: &str, layout: &Layout<'_>) -> Result<String, String> {
    let tokens = layout
        .dialect
        .tokenize(formatted)
        .map_err(|error| format!("native formatter tokenization failed: {error}"))?;
    if tokens.is_empty() {
        return Ok(formatted.to_string());
    }
    let comments = comments_in(formatted, &tokens);
    let authored = AuthoredSql {
        sql: formatted,
        tokens: &tokens,
        comments: &comments,
    };
    Ok(layout.print(&authored, oracle)?.0)
}

/// The dialect and optional line wrapping every printed layout uses.
struct Layout<'a> {
    dialect: &'a Dialect,
    wrap: Option<&'a WrapOptions<'a>>,
}

impl Layout<'_> {
    fn print(
        &self,
        authored: &AuthoredSql<'_>,
        oracle: &str,
    ) -> Result<(String, BTreeMap<usize, KeywordRecase>), String> {
        let (printed, recases) = print_authored_tokens(authored, oracle, self.dialect)?;
        let no_widths: HashMap<String, usize> = HashMap::new();
        let token_widths = self.wrap.map_or(&no_widths, |wrap| wrap.token_widths);
        let Some(mut sql) = PrintedSql::parse(&printed, self.dialect, token_widths)? else {
            return Ok((printed, recases));
        };
        sql.arrange_clauses(self.wrap.map_or(usize::MAX, |wrap| wrap.line_width));
        if let Some(wrap) = self.wrap {
            wrap_lines(&mut sql, wrap.line_width);
        }
        sql.lead_operators_of_multiline_operands();
        Ok((sql.render(), recases))
    }
}

/// Return the parse-tree layout of `neutral_sql`; only its whitespace is ever printed.
fn layout_oracle(
    neutral_sql: &str,
    semantic_tokens: &[Token],
    dialect: &Dialect,
    parse_options: &ParseOptions,
) -> Result<String, String> {
    let protected = protect_syntax(
        neutral_sql,
        semantic_tokens,
        &cast_type_token_ranges(neutral_sql, semantic_tokens)?,
        true,
    )?;
    let expressions = dialect
        .parse_with_options(&protected.sql, parse_options)
        .map_err(|error| error.to_string())?;
    let statements: Result<Vec<String>, String> = expressions
        .iter()
        .map(|expression| {
            dialect
                .generate_pretty(expression)
                .map_err(|error| error.to_string())
        })
        .collect();
    let restored = protected.restore(statements?.join(";\n"), dialect)?;
    layout_cte_macros(restored, dialect)
}

fn layout_cte_macros(mut formatted: String, dialect: &Dialect) -> Result<String, String> {
    let tokens = dialect
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

fn cast_type_token_ranges(sql: &str, tokens: &[Token]) -> Result<Vec<(usize, usize)>, String> {
    let characters: Vec<char> = sql.chars().collect();
    let mut ranges: Vec<(usize, usize)> = Vec::new();
    let mut cast_type_starts: Vec<Option<usize>> = Vec::new();
    let mut previous: Option<String> = None;
    for (index, token) in tokens.iter().enumerate() {
        let text: String = characters
            .get(token.span.start..token.span.end)
            .ok_or_else(|| UNSUPPORTED_SQL_FAILURE.to_string())?
            .iter()
            .collect();
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
