//! Print authored SQL tokens with whitespace taken from a parse-tree layout oracle.

use std::collections::{BTreeMap, BTreeSet};

use polyglot_sql::Dialect;
use polyglot_sql::tokens::{Token, TokenType};

use crate::sql_lint::constants::{CLOSE_PARENTHESIS, OPEN_PARENTHESIS};
use crate::sql_tokens::main::canonical_tokens::canonical_tokens;
use crate::sql_tokens::main::case_folding::foldable_tokens;
use crate::sql_tokens::main::is_unquoted_word::is_unquoted_word;
use crate::sql_tokens::main::name_positions::name_positions;
use crate::sql_tokens::main::token_texts::token_texts;

const TOKEN_PRESERVATION_FAILURE: &str =
    "native formatter would change authored SQL tokens, not only layout";
const COMMENT_ATTACHMENT_FAILURE: &str =
    "native formatter could not preserve comment token attachments";
const STRING_BREAK_FAILURE: &str =
    "native formatter would join adjacent string literals across a line break";
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
    /// In the reserved-keyword and built-in fold set shared with the change fingerprint.
    foldable: bool,
    /// An unquoted authored word outside the name positions that keep reserved words exact.
    recasable: bool,
    /// An unquoted word the dialect tokenizer types as a keyword.
    keyword: bool,
}

/// An authored token the printer recased to the layout guide's keyword spelling.
pub(crate) struct KeywordRecase {
    pub(crate) generated: String,
    pub(crate) keyword: bool,
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

/// Split the non-whitespace text the tokenizer skipped between two tokens into comments.
fn comments_in_gap(characters: &[char], start: usize, end: usize) -> Vec<Comment> {
    let mut comments: Vec<Comment> = Vec::new();
    let mut index = start;
    while index < end {
        if characters[index].is_whitespace() {
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
        let block = characters[index] == '/' && characters.get(index + 1) == Some(&'*');
        index = if block {
            block_comment_end(characters, start, end)
        } else {
            (start..end)
                .find(|&position| characters[position] == '\n')
                .unwrap_or(end)
        };
        comments.push(Comment {
            start,
            end: index,
            text: characters[start..index].iter().collect(),
            line: !block,
            leading,
        });
    }
    comments
}

/// End of a block comment: nested comments when they close inside the gap, else the first `*/`.
fn block_comment_end(characters: &[char], start: usize, end: usize) -> usize {
    let closes_at = |position: usize| {
        position + 1 < end && characters[position] == '*' && characters[position + 1] == '/'
    };
    let opens_at = |position: usize| {
        position + 1 < end && characters[position] == '/' && characters[position + 1] == '*'
    };
    let mut depth = 0_usize;
    let mut position = start;
    while position < end {
        if opens_at(position) {
            depth += 1;
            position += 2;
        } else if closes_at(position) {
            depth -= 1;
            position += 2;
            if depth == 0 {
                return position;
            }
        } else {
            position += 1;
        }
    }
    (start + 2..end)
        .find(|&position| closes_at(position))
        .map_or(end, |position| position + 2)
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

/// Print every authored token in order, taking only whitespace and keyword case from `oracle`.
pub(crate) fn print_authored_tokens(
    source: &AuthoredSql<'_>,
    oracle: &str,
    dialect: &Dialect,
) -> Result<(String, BTreeMap<usize, KeywordRecase>), String> {
    let AuthoredSql {
        sql,
        tokens,
        comments,
    } = *source;
    let authored = lexemes(sql, tokens, Some(dialect))?;
    let oracle_tokens = dialect
        .tokenize(oracle)
        .map_err(|error| error.to_string())?;
    let generated = lexemes(oracle, &oracle_tokens, None)?;
    let alignment = align(&authored, &generated)?;
    let oracle_characters: Vec<char> = oracle.chars().collect();
    let separators = separators(&authored, &generated, &alignment, &oracle_characters)?;
    let attached = attach_comments(tokens, comments);
    let mut output = String::with_capacity(sql.len() + sql.len() / 4);
    let string_breaks = string_breaks(sql, tokens);
    let mut recases: BTreeMap<usize, KeywordRecase> = BTreeMap::new();
    for (index, lexeme) in authored.iter().enumerate() {
        let forced_break = string_breaks.contains(&index) && !separators[index].contains('\n');
        let separator = &if forced_break {
            format!("\n{}", current_indentation(&output))
        } else {
            separators[index].clone()
        };
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
        let guide = alignment[index].map(|at| &generated[at]);
        if let Some(guide) = guide.filter(|guide| confirms_keyword(lexeme, guide)) {
            recases.insert(
                index,
                KeywordRecase {
                    generated: guide.raw.clone(),
                    keyword: guide.keyword,
                },
            );
        }
        output.push_str(&printed_text(lexeme, guide));
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
    Ok((output, recases))
}

/// Refuse output that changes anything but layout, fold-set case, and recorded keyword recases.
pub(crate) fn verify_token_invariant(
    before: &str,
    after: &str,
    dialect: &Dialect,
    recases: &BTreeMap<usize, KeywordRecase>,
) -> Result<(), String> {
    let before_tokens = tokenize(before, dialect)?;
    let after_tokens = tokenize(after, dialect)?;
    let before_canonical = canonical_tokens(before, &before_tokens, dialect)?;
    let after_canonical = canonical_tokens(after, &after_tokens, dialect)?;
    if before_canonical.len() != after_canonical.len() {
        return Err(TOKEN_PRESERVATION_FAILURE.to_string());
    }
    let before_texts = token_texts(before, &before_tokens)?;
    let after_texts = token_texts(after, &after_tokens)?;
    for (index, (left, right)) in before_canonical.iter().zip(&after_canonical).enumerate() {
        if left != right
            && !recases
                .get(&index)
                .is_some_and(|recase| recase.allows(&before_texts[index], &after_texts[index]))
        {
            return Err(TOKEN_PRESERVATION_FAILURE.to_string());
        }
    }
    if comment_positions(before, &before_tokens) != comment_positions(after, &after_tokens) {
        return Err(COMMENT_ATTACHMENT_FAILURE.to_string());
    }
    if !string_breaks(before, &before_tokens).is_subset(&string_breaks(after, &after_tokens)) {
        return Err(STRING_BREAK_FAILURE.to_string());
    }
    Ok(())
}

impl KeywordRecase {
    /// Whether `authored` became `printed` only by taking the guide's upper-case keyword spelling.
    fn allows(&self, authored: &str, printed: &str) -> bool {
        self.keyword
            && printed == self.generated
            && printed == printed.to_ascii_uppercase()
            && authored.eq_ignore_ascii_case(printed)
    }
}

fn tokenize(sql: &str, dialect: &Dialect) -> Result<Vec<Token>, String> {
    dialect.tokenize(sql).map_err(|error| error.to_string())
}

fn comment_positions(sql: &str, tokens: &[Token]) -> Vec<(String, usize)> {
    let mut positions: Vec<(String, usize)> = Vec::new();
    for comment in comments_in(sql, tokens) {
        let preceding = tokens.partition_point(|token| token.span.end <= comment.start);
        positions.push((comment.text, preceding));
    }
    positions
}

/// Lexemes of `sql`; only authored lexemes carry the recase classification.
fn lexemes(sql: &str, tokens: &[Token], dialect: Option<&Dialect>) -> Result<Vec<Lexeme>, String> {
    let raws = token_texts(sql, tokens)?;
    let (foldable, recasable) = match dialect {
        Some(dialect) => {
            let uppers: Vec<String> = raws.iter().map(|raw| raw.to_ascii_uppercase()).collect();
            let names = name_positions(&uppers);
            let foldable = foldable_tokens(&raws, tokens, dialect);
            let recasable: Vec<bool> = raws
                .iter()
                .zip(names)
                .map(|(raw, name)| !name && is_unquoted_word(raw))
                .collect();
            (foldable, recasable)
        }
        None => (vec![false; tokens.len()], vec![false; tokens.len()]),
    };
    let mut lexemes = Vec::with_capacity(tokens.len());
    for (index, (raw, token)) in raws.into_iter().zip(tokens).enumerate() {
        lexemes.push(lexeme(raw, token, foldable[index], recasable[index]));
    }
    Ok(lexemes)
}

fn lexeme(raw: String, token: &Token, foldable: bool, recasable: bool) -> Lexeme {
    let key = if is_unquoted_word(&raw) {
        format!("w:{}", raw.to_ascii_uppercase())
    } else if raw
        .chars()
        .all(|character| character.is_ascii_punctuation())
    {
        format!("p:{:?}", token.token_type)
    } else {
        format!("r:{raw}")
    };
    let keyword = is_unquoted_word(&raw)
        && !matches!(
            token.token_type,
            TokenType::Var | TokenType::Identifier | TokenType::QuotedIdentifier
        );
    Lexeme {
        start: token.span.start,
        end: token.span.end,
        raw,
        key,
        foldable,
        recasable,
        keyword,
    }
}

fn is_string_literal(token: &Token) -> bool {
    matches!(
        token.token_type,
        TokenType::String
            | TokenType::NationalString
            | TokenType::EscapeString
            | TokenType::RawString
            | TokenType::ByteString
            | TokenType::UnicodeString
            | TokenType::HexString
            | TokenType::BitString
            | TokenType::DollarString
            | TokenType::TripleSingleQuotedString
            | TokenType::TripleDoubleQuotedString
    )
}

/// Indices of string literals that follow another string literal across a line break.
fn string_breaks(sql: &str, tokens: &[Token]) -> BTreeSet<usize> {
    let characters: Vec<char> = sql.chars().collect();
    (1..tokens.len())
        .filter(|&index| {
            is_string_literal(&tokens[index - 1])
                && is_string_literal(&tokens[index])
                && characters[tokens[index - 1].span.end..tokens[index].span.start].contains(&'\n')
        })
        .collect()
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
            let oracle_gap = (previous_at + 1..next_at)
                .rev()
                .find(|&at| generated[at].key == authored[last].key)
                .map_or_else(|| gap(next_at - 1, next_at), |at| gap(at, at + 1));
            let unspaced = default_space(&authored[last], &authored[next]).is_empty();
            if unspaced && !oracle_gap.contains('\n') {
                String::new()
            } else {
                oracle_gap
            }
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
        let call =
            is_unquoted_word(&authored[index - 1].raw) && authored[index].raw == OPEN_PARENTHESIS;
        let inside_parentheses =
            authored[index - 1].raw == OPEN_PARENTHESIS || authored[index].raw == CLOSE_PARENTHESIS;
        if (adjacent_in_source && !oracle_pair && (!structural || call))
            || (inside_parentheses && !separators[index].contains('\n'))
        {
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

/// The authored text, recased only for keywords and built-in function names.
fn printed_text(authored: &Lexeme, generated: Option<&Lexeme>) -> String {
    if let Some(generated) = generated.filter(|generated| confirms_keyword(authored, generated)) {
        return generated.raw.clone();
    }
    if !authored.foldable {
        return authored.raw.clone();
    }
    match generated {
        Some(generated) if generated.raw.eq_ignore_ascii_case(&authored.raw) => {
            generated.raw.clone()
        }
        Some(_) => authored.raw.clone(),
        None => authored.raw.to_ascii_uppercase(),
    }
}

/// Whether the layout guide prints the aligned authored word as an upper-case keyword.
fn confirms_keyword(authored: &Lexeme, generated: &Lexeme) -> bool {
    !authored.foldable
        && authored.recasable
        && generated.keyword
        && generated.raw != authored.raw
        && generated.raw == generated.raw.to_ascii_uppercase()
        && generated.raw.eq_ignore_ascii_case(&authored.raw)
}

fn attach_comments<'a>(tokens: &[Token], comments: &'a [Comment]) -> Vec<Attached<'a>> {
    let mut attached: Vec<Attached<'a>> = (0..tokens.len()).map(|_| Attached::default()).collect();
    for comment in comments {
        let next = tokens.partition_point(|token| token.span.start < comment.end);
        let preceding = tokens.partition_point(|token| token.span.end <= comment.start);
        let next = (next < tokens.len()).then_some(next);
        let previous = preceding.checked_sub(1);
        match (comment.leading, next, previous) {
            (true, Some(next), _) | (false, Some(next), None) => {
                attached[next].leading.push(comment);
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
