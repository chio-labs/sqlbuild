//! PyYAML's `scan_block_scalar`, which reads literal and folded scalars and chomps their tails.

use crate::constants::BYTE_ORDER_MARK;
use crate::yaml::constants::{KEEP_INDICATOR, STRIP_INDICATOR};

const END: char = '\0';
const FOLDED_INDICATOR: char = '>';
const LINE_FEED: &str = "\n";
const DIGITS: [char; 10] = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'];

fn is_break(character: char) -> bool {
    matches!(character, '\r' | '\n' | '\u{85}' | '\u{2028}' | '\u{2029}')
}

fn is_blank(character: char) -> bool {
    matches!(character, ' ' | '\t')
}

/// The column of char index `index`, counted as PyYAML's reader counts it.
pub(crate) fn column_of(chars: &[char], index: usize) -> usize {
    let line_start = chars[..index.min(chars.len())]
        .iter()
        .rposition(|character| is_break(*character))
        .map_or(0, |line_break| line_break + 1);
    chars[line_start..index.min(chars.len())]
        .iter()
        .filter(|character| **character != BYTE_ORDER_MARK)
        .count()
}

/// PyYAML's scanner position over the document characters.
struct BlockScanner<'chars> {
    chars: &'chars [char],
    index: usize,
    column: usize,
}

impl BlockScanner<'_> {
    fn peek(&self, offset: usize) -> char {
        self.chars.get(self.index + offset).copied().unwrap_or(END)
    }

    fn forward(&mut self, count: usize) {
        for _ in 0..count {
            let character = self.peek(0);
            self.index += 1;
            if matches!(character, '\n' | '\u{85}' | '\u{2028}' | '\u{2029}')
                || (character == '\r' && self.peek(0) != '\n')
            {
                self.column = 0;
            } else if character != BYTE_ORDER_MARK {
                self.column += 1;
            }
        }
    }

    fn line_break(&mut self) -> String {
        match self.peek(0) {
            '\r' if self.peek(1) == '\n' => {
                self.forward(2);
                "\n".to_owned()
            }
            '\r' | '\n' | '\u{85}' => {
                self.forward(1);
                "\n".to_owned()
            }
            separator @ ('\u{2028}' | '\u{2029}') => {
                self.forward(1);
                separator.to_string()
            }
            _ => String::new(),
        }
    }

    fn at_line_end(&self) -> bool {
        self.peek(0) == END || is_break(self.peek(0))
    }

    /// An indentation digit: `Some(None)` when absent and `None` for the invalid `0`.
    fn digit(&mut self) -> Option<Option<usize>> {
        let Some(increment) = DIGITS.iter().position(|digit| *digit == self.peek(0)) else {
            return Some(None);
        };
        self.forward(1);
        (increment > 0).then_some(Some(increment))
    }

    fn chomping(&mut self) -> Option<bool> {
        let character = self.peek(0);
        let chomping = matches!(character, KEEP_INDICATOR | STRIP_INDICATOR);
        chomping.then(|| {
            self.forward(1);
            character == KEEP_INDICATOR
        })
    }

    /// `scan_block_scalar_indicators`: the chomping flag and the explicit indentation increment.
    fn indicators(&mut self) -> Option<(Option<bool>, Option<usize>)> {
        let indicators = match self.chomping() {
            Some(chomping) => (Some(chomping), self.digit()?),
            None => {
                let increment = self.digit()?;
                (self.chomping(), increment)
            }
        };
        (self.peek(0) == ' ' || self.at_line_end()).then_some(indicators)
    }

    /// `scan_block_scalar_ignored_line`: spaces and a comment after the indicators.
    fn ignored_line(&mut self) -> Option<()> {
        while self.peek(0) == ' ' {
            self.forward(1);
        }
        if self.peek(0) == '#' {
            while !self.at_line_end() {
                self.forward(1);
            }
        }
        self.at_line_end().then(|| {
            self.line_break();
        })
    }

    /// `scan_block_scalar_indentation`: leading empty lines and the deepest indentation among them.
    fn indentation(&mut self) -> (String, usize) {
        let mut breaks = String::new();
        let mut max_indent = 0;
        while self.peek(0) == ' ' || is_break(self.peek(0)) {
            if self.peek(0) == ' ' {
                self.forward(1);
                max_indent = max_indent.max(self.column);
            } else {
                breaks.push_str(&self.line_break());
            }
        }
        (breaks, max_indent)
    }

    /// `scan_block_scalar_breaks`: empty lines up to the next line indented to `indent`.
    fn breaks(&mut self, indent: usize) -> String {
        let mut breaks = String::new();
        while self.column < indent && self.peek(0) == ' ' {
            self.forward(1);
        }
        while is_break(self.peek(0)) {
            breaks.push_str(&self.line_break());
            while self.column < indent && self.peek(0) == ' ' {
                self.forward(1);
            }
        }
        breaks
    }

    fn line(&mut self) -> String {
        let start = self.index;
        let mut length = 0;
        while !(self.peek(length) == END || is_break(self.peek(length))) {
            length += 1;
        }
        self.forward(length);
        self.chars[start..start + length].iter().collect()
    }
}

/// Read the block scalar whose indicator is at `indicator`, under a block collection at `parent_indent`.
pub(crate) fn scan_block_scalar(
    chars: &[char],
    indicator: usize,
    parent_indent: Option<usize>,
) -> Option<(String, usize)> {
    let folded = chars.get(indicator) == Some(&FOLDED_INDICATOR);
    let mut scanner = BlockScanner {
        chars,
        index: indicator,
        column: column_of(chars, indicator),
    };
    scanner.forward(1);
    let (chomping, increment) = scanner.indicators()?;
    scanner.ignored_line()?;
    let min_indent = parent_indent.map_or(1, |indent| indent + 1);
    let (mut breaks, indent) = match increment {
        None => {
            let (breaks, max_indent) = scanner.indentation();
            (breaks, min_indent.max(max_indent))
        }
        Some(increment) => {
            let indent = min_indent + increment - 1;
            (scanner.breaks(indent), indent)
        }
    };
    let mut value = String::new();
    let mut line_break = String::new();
    while scanner.column == indent && scanner.peek(0) != END {
        value.push_str(&breaks);
        let leading_non_space = !is_blank(scanner.peek(0));
        value.push_str(&scanner.line());
        line_break = scanner.line_break();
        breaks = scanner.breaks(indent);
        if scanner.column != indent || scanner.peek(0) == END {
            break;
        }
        let joins_with_space =
            folded && line_break == LINE_FEED && leading_non_space && !is_blank(scanner.peek(0));
        match (joins_with_space, breaks.is_empty()) {
            (true, true) => value.push(' '),
            (true, false) => {}
            (false, _) => value.push_str(&line_break),
        }
    }
    if chomping != Some(false) {
        value.push_str(&line_break);
    }
    if chomping == Some(true) {
        value.push_str(&breaks);
    }
    Some((value, scanner.index))
}
