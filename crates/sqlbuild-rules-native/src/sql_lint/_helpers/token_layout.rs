//! Print authored SQL tokens with whitespace taken from a parse-tree layout oracle.

use polyglot_sql::Dialect;
use polyglot_sql::tokens::{Token, TokenType};

use crate::sql_tokens::main::canonical_tokens::canonical_tokens;
use crate::sql_tokens::main::is_unquoted_word::is_unquoted_word;

const TOKEN_PRESERVATION_FAILURE: &str =
    "native formatter would change authored SQL tokens, not only layout";
const COMMENT_ATTACHMENT_FAILURE: &str =
    "native formatter could not preserve comment token attachments";
const ALIGNMENT_FAILURE: &str = "native formatter could not align its layout with authored tokens";
const RESYNC_WINDOW: usize = 48;
const RESYNC_CONFIRMATION: usize = 1;
const NO_SPACE_BEFORE: [&str; 7] = [",", ")", "]", ".", ";", "::", ":"];
const NO_SPACE_AFTER: [&str; 5] = ["(", "[", ".", "::", ":"];
const STRUCTURAL_PUNCTUATION: [&str; 6] = ["(", ")", "[", "]", ",", ";"];

#[derive(Debug, Clone)]
pub(crate) struct Comment {
    pub(crate) start: usize,
    pub(crate) end: usize,
    pub(crate) text: String,
    pub(crate) line: bool,
    pub(crate) leading: bool,
}

/// One authored or oracle token with its raw source text and alignment key.
struct Lexeme {
    start: usize,
    end: usize,
    raw: String,
    key: String,
    keyword: bool,
}

/// Comments attached to the authored token they precede or follow.
#[derive(Default)]
struct Attached<'a> {
    leading: Vec<&'a Comment>,
    trailing: Vec<&'a Comment>,
}

pub(crate) fn comments_in(sql: &str, tokens: &[Token]) -> Vec<Comment> {
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

pub(crate) fn neutralize_comments(sql: &str, comments: &[Comment]) -> String {
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

/// Authored SQL text with its dialect tokens and the comments between them.
pub(crate) struct AuthoredSql<'a> {
    pub(crate) sql: &'a str,
    pub(crate) tokens: &'a [Token],
    pub(crate) comments: &'a [Comment],
}

/// Print every authored token in order, taking only whitespace and word case from `oracle`.
pub(crate) fn print_authored_tokens(
    source: &AuthoredSql<'_>,
    oracle: &str,
    dialect: &Dialect,
) -> Result<String, String> {
    let AuthoredSql {
        sql,
        tokens,
        comments,
    } = *source;
    let authored = lexemes(sql, tokens)?;
    let oracle_tokens = dialect
        .tokenize(oracle)
        .map_err(|error| error.to_string())?;
    let generated = lexemes(oracle, &oracle_tokens)?;
    let alignment = align(&authored, &generated)?;
    let oracle_characters: Vec<char> = oracle.chars().collect();
    let separators = separators(&authored, &generated, &alignment, &oracle_characters)?;
    let attached = attach_comments(tokens, comments);
    let mut output = String::with_capacity(sql.len() + sql.len() / 4);
    for (index, lexeme) in authored.iter().enumerate() {
        let separator = &separators[index];
        let leading = &attached[index].leading;
        if leading.is_empty() {
            output.push_str(separator);
        } else if index == 0 || separator.contains('\n') {
            output.push_str(separator);
            let indentation = current_indentation(&output);
            for comment in leading {
                output.push_str(&comment.text);
                output.push('\n');
                output.push_str(&indentation);
            }
        } else {
            let indentation = current_indentation(&output);
            for comment in leading {
                output.push('\n');
                output.push_str(&indentation);
                output.push_str(&comment.text);
            }
            output.push('\n');
            output.push_str(&indentation);
        }
        output.push_str(&printed_text(
            lexeme,
            alignment[index].map(|at| &generated[at]),
        ));
        let trailing = &attached[index].trailing;
        for (position, comment) in trailing.iter().enumerate() {
            output.push(' ');
            output.push_str(&comment.text);
            if !comment.line {
                continue;
            }
            let next_starts_line = if position + 1 < trailing.len() {
                false
            } else {
                separators
                    .get(index + 1)
                    .is_some_and(|next| next.starts_with('\n'))
            };
            if !next_starts_line {
                output.push('\n');
                if position + 1 < trailing.len() {
                    output.push_str(&current_indentation(&output));
                }
            }
        }
    }
    Ok(output)
}

/// Refuse any output whose canonical tokens or comment attachments differ from the input.
pub(crate) fn verify_token_invariant(
    before: &str,
    after: &str,
    dialect: &Dialect,
) -> Result<(), String> {
    if canonical_tokens(before, dialect)? != canonical_tokens(after, dialect)? {
        return Err(TOKEN_PRESERVATION_FAILURE.to_string());
    }
    if comment_positions(before, dialect)? != comment_positions(after, dialect)? {
        return Err(COMMENT_ATTACHMENT_FAILURE.to_string());
    }
    Ok(())
}

fn comment_positions(sql: &str, dialect: &Dialect) -> Result<Vec<(String, usize)>, String> {
    let tokens = dialect.tokenize(sql).map_err(|error| error.to_string())?;
    let mut positions: Vec<(String, usize)> = Vec::new();
    for comment in comments_in(sql, &tokens) {
        let preceding = tokens
            .iter()
            .take_while(|token| token.span.end <= comment.start)
            .count();
        positions.push((comment.text, preceding));
    }
    Ok(positions)
}

fn lexemes(sql: &str, tokens: &[Token]) -> Result<Vec<Lexeme>, String> {
    let characters: Vec<char> = sql.chars().collect();
    let mut lexemes: Vec<Lexeme> = Vec::with_capacity(tokens.len());
    for token in tokens {
        lexemes.push(lexeme(&characters, token)?);
    }
    Ok(lexemes)
}

fn lexeme(characters: &[char], token: &Token) -> Result<Lexeme, String> {
    let raw: String = characters
        .get(token.span.start..token.span.end)
        .ok_or_else(|| TOKEN_PRESERVATION_FAILURE.to_string())?
        .iter()
        .collect();
    let word = is_unquoted_word(&raw);
    let key = if word {
        format!("w:{}", raw.to_ascii_uppercase())
    } else if raw
        .chars()
        .all(|character| character.is_ascii_punctuation())
    {
        format!("p:{:?}", token.token_type)
    } else {
        format!("r:{raw}")
    };
    let keyword = word && !matches!(token.token_type, TokenType::Var | TokenType::Identifier);
    Ok(Lexeme {
        start: token.span.start,
        end: token.span.end,
        raw,
        key,
        keyword,
    })
}

/// Map authored tokens to matching oracle tokens; a closer only matches its opener's partner.
fn align(authored: &[Lexeme], generated: &[Lexeme]) -> Result<Vec<Option<usize>>, String> {
    let mut state = Alignment {
        authored,
        generated,
        authored_partners: bracket_partners(authored),
        generated_partners: bracket_partners(generated),
        forward: vec![None; authored.len()],
        backward: vec![None; generated.len()],
    };
    let (mut left, mut right) = (0_usize, 0_usize);
    while left < authored.len() && right < generated.len() {
        if state.matches(left, right) {
            state.forward[left] = Some(right);
            state.backward[right] = Some(left);
            left += 1;
            right += 1;
            continue;
        }
        let (skip_left, skip_right) = state
            .resync(left, right)
            .ok_or_else(|| ALIGNMENT_FAILURE.to_string())?;
        left += skip_left;
        right += skip_right;
    }
    Ok(state.forward)
}

struct Alignment<'a> {
    authored: &'a [Lexeme],
    generated: &'a [Lexeme],
    authored_partners: Vec<Option<usize>>,
    generated_partners: Vec<Option<usize>>,
    forward: Vec<Option<usize>>,
    backward: Vec<Option<usize>>,
}

impl Alignment<'_> {
    fn matches(&self, left: usize, right: usize) -> bool {
        if self.authored[left].key != self.generated[right].key {
            return false;
        }
        if !is_closer(&self.authored[left].raw) {
            return true;
        }
        match (self.authored_partners[left], self.generated_partners[right]) {
            (Some(opener), Some(generated_opener)) => match self.forward[opener] {
                Some(aligned) => aligned == generated_opener,
                None => self.backward[generated_opener].is_none(),
            },
            (None, None) => true,
            _ => false,
        }
    }

    fn resync(&self, left: usize, right: usize) -> Option<(usize, usize)> {
        let remaining_left = self.authored.len() - left;
        let remaining_right = self.generated.len() - right;
        for cost in 1..=(2 * RESYNC_WINDOW) {
            for skip_left in 0..=cost.min(RESYNC_WINDOW) {
                let skip_right = cost - skip_left;
                if skip_right > RESYNC_WINDOW {
                    continue;
                }
                if skip_left >= remaining_left || skip_right >= remaining_right {
                    if skip_left >= remaining_left && skip_right >= remaining_right {
                        return Some((remaining_left, remaining_right));
                    }
                    continue;
                }
                if !self.matches(left + skip_left, right + skip_right) {
                    continue;
                }
                let anchor = &self.authored[left + skip_left];
                let confirmations = if anchor.key.starts_with("p:") {
                    RESYNC_CONFIRMATION
                } else {
                    0
                };
                let confirmed = (1..=confirmations).all(|offset| {
                    match (
                        self.authored.get(left + skip_left + offset),
                        self.generated.get(right + skip_right + offset),
                    ) {
                        (Some(before), Some(after)) => before.key == after.key,
                        _ => true,
                    }
                });
                if confirmed {
                    return Some((skip_left, skip_right));
                }
            }
        }
        None
    }
}

fn is_closer(raw: &str) -> bool {
    matches!(raw, ")" | "]" | "}")
}

fn bracket_partners(lexemes: &[Lexeme]) -> Vec<Option<usize>> {
    let mut partners: Vec<Option<usize>> = vec![None; lexemes.len()];
    let mut open: Vec<usize> = Vec::new();
    for (index, lexeme) in lexemes.iter().enumerate() {
        match lexeme.raw.as_str() {
            "(" | "[" | "{" => open.push(index),
            ")" | "]" | "}" => {
                if let Some(opener) = open.pop() {
                    partners[opener] = Some(index);
                    partners[index] = Some(opener);
                }
            }
            _ => {}
        }
    }
    partners
}

fn separators(
    authored: &[Lexeme],
    generated: &[Lexeme],
    alignment: &[Option<usize>],
    oracle: &[char],
) -> Result<Vec<String>, String> {
    let mut separators: Vec<String> = vec![String::new(); authored.len()];
    let anchors: Vec<usize> = (0..authored.len())
        .filter(|&index| alignment[index].is_some())
        .collect();
    if anchors.is_empty() {
        return Err(ALIGNMENT_FAILURE.to_string());
    }
    let gap = |left: usize, right: usize| -> String {
        oracle[generated[left].end..generated[right].start]
            .iter()
            .collect()
    };
    for index in 1..anchors[0] {
        separators[index] = default_space(&authored[index - 1], &authored[index]).to_string();
    }
    if anchors[0] > 0 {
        separators[anchors[0]] =
            default_space(&authored[anchors[0] - 1], &authored[anchors[0]]).to_string();
    }
    for pair in anchors.windows(2) {
        let (previous, next) = (pair[0], pair[1]);
        let (previous_at, next_at) = (
            alignment[previous].ok_or(ALIGNMENT_FAILURE)?,
            alignment[next].ok_or(ALIGNMENT_FAILURE)?,
        );
        let merged = merged_gap(
            &(previous_at..next_at)
                .map(|at| gap(at, at + 1))
                .collect::<Vec<_>>(),
        );
        if previous + 1 == next {
            separators[next] = merged;
            continue;
        }
        for index in previous + 2..next {
            separators[index] = default_space(&authored[index - 1], &authored[index]).to_string();
        }
        let first = previous + 1;
        let last = next - 1;
        let substitution = next_at > previous_at + 1;
        separators[first] = if default_space(&authored[previous], &authored[first]).is_empty() {
            String::new()
        } else if substitution {
            gap(previous_at, previous_at + 1)
        } else {
            " ".to_string()
        };
        separators[next] = if substitution {
            gap(next_at - 1, next_at)
        } else if merged.contains('\n') {
            merged
        } else {
            default_space(&authored[last], &authored[next]).to_string()
        };
    }
    let last_anchor = anchors[anchors.len() - 1];
    for index in last_anchor + 1..authored.len() {
        separators[index] = default_space(&authored[index - 1], &authored[index]).to_string();
    }
    let last_at = alignment[last_anchor].ok_or(ALIGNMENT_FAILURE)?;
    if last_anchor + 1 < authored.len()
        && last_at + 1 < generated.len()
        && !separators[last_anchor + 1].is_empty()
    {
        separators[last_anchor + 1] = gap(last_at, last_at + 1);
    }
    for index in 1..authored.len() {
        let adjacent_in_source = authored[index - 1].end == authored[index].start;
        let oracle_pair = matches!(
            (alignment[index - 1], alignment[index]),
            (Some(previous), Some(next)) if previous + 1 == next
        );
        let structural = [&authored[index - 1], &authored[index]]
            .iter()
            .any(|lexeme| STRUCTURAL_PUNCTUATION.contains(&lexeme.raw.as_str()));
        if adjacent_in_source && !oracle_pair && !structural {
            separators[index].clear();
        } else if separators[index].is_empty()
            && !adjacent_in_source
            && would_fuse(&authored[index - 1], &authored[index])
        {
            separators[index] = " ".to_string();
        }
    }
    Ok(separators)
}

fn merged_gap(gaps: &[String]) -> String {
    if let [only] = gaps {
        return only.clone();
    }
    if let Some(newline) = gaps.iter().rev().find(|gap| gap.contains('\n')) {
        return newline.clone();
    }
    if gaps.iter().any(|gap| !gap.is_empty()) {
        " ".to_string()
    } else {
        String::new()
    }
}

fn default_space(previous: &Lexeme, next: &Lexeme) -> &'static str {
    if NO_SPACE_BEFORE.contains(&next.raw.as_str())
        || NO_SPACE_AFTER.contains(&previous.raw.as_str())
    {
        ""
    } else {
        " "
    }
}

/// Return whether printing two separated tokens without a space could lex them differently.
fn would_fuse(previous: &Lexeme, next: &Lexeme) -> bool {
    let (Some(left), Some(right)) = (previous.raw.chars().last(), next.raw.chars().next()) else {
        return false;
    };
    let word = |character: char| {
        character.is_alphanumeric() || matches!(character, '_' | '$' | '\'' | '"' | '`' | '@')
    };
    let operator = |character: char| "+-*/<>=!|&^%~:#?".contains(character);
    (word(left) && word(right)) || (operator(left) && operator(right))
}

fn printed_text(authored: &Lexeme, generated: Option<&Lexeme>) -> String {
    match generated {
        Some(generated)
            if generated.raw != authored.raw
                && is_unquoted_word(&authored.raw)
                && generated.raw.eq_ignore_ascii_case(&authored.raw) =>
        {
            generated.raw.clone()
        }
        None if authored.keyword => authored.raw.to_ascii_uppercase(),
        _ => authored.raw.clone(),
    }
}

fn attach_comments<'a>(tokens: &[Token], comments: &'a [Comment]) -> Vec<Attached<'a>> {
    let mut attached: Vec<Attached<'a>> = (0..tokens.len()).map(|_| Attached::default()).collect();
    for comment in comments {
        let next = tokens
            .iter()
            .position(|token| token.span.start >= comment.end);
        let previous = tokens
            .iter()
            .rposition(|token| token.span.end <= comment.start);
        match (comment.leading, next, previous) {
            (true, Some(next), _) | (false, Some(next), None) => {
                attached[next].leading.push(comment)
            }
            (_, _, Some(previous)) => attached[previous].trailing.push(comment),
            (_, None, None) => {}
        }
    }
    attached
}

fn current_indentation(output: &str) -> String {
    let line = output.rsplit('\n').next().unwrap_or_default();
    line.chars()
        .take_while(|character| *character == ' ' || *character == '\t')
        .collect()
}
