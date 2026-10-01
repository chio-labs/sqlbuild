//! Break printed SQL lines longer than the line width at structural token boundaries.

use std::collections::HashMap;

use polyglot_sql::Dialect;

const CONTINUATION_INDENT: usize = 2;
const CHAIN_KEYWORDS: [&str; 2] = ["AND", "OR"];
const ARITHMETIC_OPERATORS: [&str; 5] = ["+", "-", "||", "/", "%"];
const COMMA: &str = ",";
const SINGLE_SPACE: &str = " ";
const BETWEEN_KEYWORD: &str = "BETWEEN";
const BETWEEN_SEPARATOR: &str = "AND";
const WINDOW_CLAUSE_KEYWORDS: [&str; 4] = ["ORDER", "ROWS", "RANGE", "GROUPS"];

/// Line width and the printed widths of tokens that stand in for longer authored text.
pub(crate) struct WrapOptions<'a> {
    pub(crate) line_width: usize,
    pub(crate) token_widths: &'a HashMap<String, usize>,
}

/// Printed SQL as tokens and the whitespace or comment text before each token.
struct Printed<'a> {
    tokens: Vec<String>,
    gaps: Vec<String>,
    depths: Vec<usize>,
    partners: Vec<Option<usize>>,
    options: &'a WrapOptions<'a>,
}

/// One printed line; end columns are absent when comments or multi-line tokens pin it.
struct Line {
    first: usize,
    last: usize,
    indentation: usize,
    end_columns: Option<Vec<usize>>,
}

/// Re-break every line of `sql` that is longer than the line width and can be shortened.
pub(crate) fn wrap_lines(
    sql: &str,
    dialect: &Dialect,
    options: &WrapOptions<'_>,
) -> Result<String, String> {
    let tokens = dialect
        .tokenize(sql)
        .map_err(|error| format!("native formatter tokenization failed: {error}"))?;
    if tokens.is_empty() {
        return Ok(sql.to_string());
    }
    let characters: Vec<char> = sql.chars().collect();
    let mut texts: Vec<String> = Vec::with_capacity(tokens.len());
    let mut gaps: Vec<String> = Vec::with_capacity(tokens.len() + 1);
    let mut previous_end = 0_usize;
    for token in &tokens {
        gaps.push(characters[previous_end..token.span.start].iter().collect());
        texts.push(
            characters[token.span.start..token.span.end]
                .iter()
                .collect(),
        );
        previous_end = token.span.end;
    }
    gaps.push(characters[previous_end..].iter().collect());
    let (depths, partners) = bracket_structure(&texts);
    let mut printed = Printed {
        tokens: texts,
        gaps,
        depths,
        partners,
        options,
    };
    let mut pending: Vec<(usize, usize)> = printed.line_ranges(0, printed.tokens.len() - 1);
    pending.reverse();
    while let Some((first, last)) = pending.pop() {
        let line = printed.line(first, last);
        if !printed.overflows(&line) || !printed.break_line(&line) {
            continue;
        }
        let mut lines = printed.line_ranges(first, last);
        lines.reverse();
        pending.extend(lines);
    }
    Ok(printed.render())
}

fn bracket_structure(tokens: &[String]) -> (Vec<usize>, Vec<Option<usize>>) {
    let mut depths: Vec<usize> = Vec::with_capacity(tokens.len());
    let mut partners: Vec<Option<usize>> = vec![None; tokens.len()];
    let mut open: Vec<usize> = Vec::new();
    for (index, token) in tokens.iter().enumerate() {
        match token.as_str() {
            "(" | "[" | "{" => {
                depths.push(open.len());
                open.push(index);
            }
            ")" | "]" | "}" => {
                let opener = open.pop();
                depths.push(open.len());
                if let Some(opener) = opener {
                    partners[opener] = Some(index);
                    partners[index] = Some(opener);
                }
            }
            _ => depths.push(open.len()),
        }
    }
    (depths, partners)
}

impl Printed<'_> {
    fn line_ranges(&self, first: usize, last: usize) -> Vec<(usize, usize)> {
        let mut ranges: Vec<(usize, usize)> = Vec::new();
        let mut start = first;
        for index in first + 1..=last {
            if self.gaps[index].contains('\n') {
                ranges.push((start, index - 1));
                start = index;
            }
        }
        ranges.push((start, last));
        ranges
    }

    fn line(&self, first: usize, last: usize) -> Line {
        let lead = self.gaps[first].rsplit('\n').next().unwrap_or_default();
        let indentation = lead.chars().count();
        let trailing = self.gaps[last + 1].split('\n').next().unwrap_or_default();
        let commented = !lead.trim().is_empty()
            || !trailing.trim().is_empty()
            || (first + 1..=last).any(|index| !self.gaps[index].trim().is_empty());
        let multiline = (first..=last).any(|index| self.tokens[index].contains('\n'));
        let end_columns = (!commented && !multiline).then(|| {
            let mut column = indentation;
            let mut ends: Vec<usize> = Vec::with_capacity(last - first + 1);
            for index in first..=last {
                if index > first {
                    column += self.gaps[index].chars().count();
                }
                column += self.width(index);
                ends.push(column);
            }
            ends
        });
        Line {
            first,
            last,
            indentation,
            end_columns,
        }
    }

    fn width(&self, index: usize) -> usize {
        let token = &self.tokens[index];
        self.options
            .token_widths
            .get(&token.to_ascii_uppercase())
            .copied()
            .unwrap_or_else(|| token.chars().count())
    }

    fn overflows(&self, line: &Line) -> bool {
        line.end_columns.as_ref().is_some_and(|ends| {
            ends.last()
                .is_some_and(|end| *end > self.options.line_width)
        })
    }

    /// Apply the outermost applicable break: top-level chains, then bracket groups, then commas.
    fn break_line(&mut self, line: &Line) -> bool {
        self.break_before(line, &CHAIN_KEYWORDS, 0)
            || self.break_before(line, &ARITHMETIC_OPERATORS, CONTINUATION_INDENT)
            || self.explode_group(line)
            || self.break_after_commas(line)
    }

    /// Put the arguments of the outermost bracket group that crosses the limit on their own lines.
    fn explode_group(&mut self, line: &Line) -> bool {
        let Some(ends) = line.end_columns.as_ref() else {
            return false;
        };
        let mut chosen: Option<(usize, usize)> = None;
        for opener in line.first..=line.last {
            let Some(closer) = self.partners[opener] else {
                continue;
            };
            if closer <= opener + 2
                || closer > line.last
                || !matches!(self.tokens[opener].as_str(), "(" | "[" | "{")
                || ends[closer - line.first] <= self.options.line_width
            {
                continue;
            }
            if chosen.is_none_or(|(best, _)| self.depths[opener] < self.depths[best]) {
                chosen = Some((opener, closer));
            }
        }
        let Some((opener, closer)) = chosen else {
            return false;
        };
        let inner = newline(line.indentation + CONTINUATION_INDENT);
        let window = opener > 0 && self.tokens[opener - 1].eq_ignore_ascii_case("OVER");
        self.gaps[opener + 1] = inner.clone();
        self.gaps[closer] = newline(line.indentation);
        for index in opener + 2..closer {
            if self.depths[index] != self.depths[opener] + 1 {
                continue;
            }
            if window {
                if WINDOW_CLAUSE_KEYWORDS
                    .contains(&self.tokens[index].to_ascii_uppercase().as_str())
                {
                    self.gaps[index] = inner.clone();
                }
            } else if self.tokens[index - 1] == COMMA {
                self.gaps[index] = inner.clone();
            }
        }
        true
    }

    /// Break before every operator of `operators` at the line's outermost depth.
    fn break_before(&mut self, line: &Line, operators: &[&str], extra_indent: usize) -> bool {
        let depth = self.line_depth(line);
        let mut between = false;
        let mut breaks: Vec<usize> = Vec::new();
        for index in line.first..=line.last {
            if self.depths[index] != depth {
                continue;
            }
            let upper = self.tokens[index].to_ascii_uppercase();
            if upper == BETWEEN_KEYWORD {
                between = true;
                continue;
            }
            if upper == BETWEEN_SEPARATOR && between {
                between = false;
                continue;
            }
            if index > line.first
                && operators.contains(&upper.as_str())
                && self.gaps[index] == SINGLE_SPACE
                && ends_operand(&self.tokens[index - 1])
            {
                breaks.push(index);
            }
        }
        let indentation = newline(line.indentation + extra_indent);
        for index in &breaks {
            self.gaps[*index] = indentation.clone();
        }
        !breaks.is_empty()
    }

    /// Break after every comma at the line's outermost depth.
    fn break_after_commas(&mut self, line: &Line) -> bool {
        let depth = self.line_depth(line);
        let indentation = newline(line.indentation + CONTINUATION_INDENT);
        let mut changed = false;
        for index in line.first..line.last {
            if self.depths[index] == depth && self.tokens[index] == COMMA {
                self.gaps[index + 1] = indentation.clone();
                changed = true;
            }
        }
        changed
    }

    fn line_depth(&self, line: &Line) -> usize {
        (line.first..=line.last)
            .map(|index| self.depths[index])
            .min()
            .unwrap_or_default()
    }

    fn render(&self) -> String {
        let mut output = String::new();
        for (gap, token) in self.gaps.iter().zip(&self.tokens) {
            output.push_str(gap);
            output.push_str(token);
        }
        output.push_str(&self.gaps[self.tokens.len()]);
        output
    }
}

fn ends_operand(token: &str) -> bool {
    token.chars().last().is_some_and(|character| {
        character.is_alphanumeric() || matches!(character, '_' | '\'' | '"' | '`' | ')' | ']')
    })
}

fn newline(indentation: usize) -> String {
    format!("\n{}", " ".repeat(indentation))
}
