//! An exact port of `scan_interpolation_sites`: SQLBuild interpolation sites outside comments and
//! strings, with the lint lexical policy (`neutralize_interpolation` without formatting).

use sqlbuild_core::text::main::is_python_alnum::is_python_alnum;
use sqlbuild_core::text::main::is_python_alpha::is_python_alpha;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::models::PythonText;

use crate::refactoring::_helpers::chars::{find, slice, starts_with};

/// The reference functions the lint scan pattern matches, in `sorted()` order.
const REFERENCE_FUNCTIONS: [&str; 6] = [
    "__dbt_ref",
    "__ref",
    "__seed",
    "__source",
    "__table_fn",
    "__udf",
];
/// Every SQLBuild function name `_interpolation_site_end` accepts.
const FUNCTION_NAMES: [&str; 9] = [
    "__cursor_start",
    "__cursor_end",
    "__empty_fixture",
    "__dbt_ref",
    "__table_fn",
    "__source",
    "__seed",
    "__udf",
    "__ref",
];
const INTERPOLATION_NAME_EXTRA: [char; 3] = ['_', ':', '.'];

/// One interpolation site in original text offsets.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct InterpolationSite {
    pub(crate) start: usize,
    pub(crate) end: usize,
    pub(crate) text: String,
}

/// Every interpolation site of `body`, as `scan_interpolation_sites(body=..., dialect=...)`.
pub(crate) fn interpolation_sites(
    body: &[char],
    backtick_identifiers: bool,
    python: PythonText,
) -> Vec<InterpolationSite> {
    let scanner = Scanner {
        body,
        backtick_identifiers,
        python,
    };
    let mut sites: Vec<InterpolationSite> = Vec::new();
    let mut copied_to = 0;
    let mut index = 0;
    while index < body.len() {
        match scanner.pattern_match(index) {
            Some(PatternMatch::NonCode(end)) => index = end,
            Some(PatternMatch::Site(end)) => {
                if index >= copied_to
                    && let Some(site_end) = scanner.site_end(index)
                {
                    sites.push(InterpolationSite {
                        start: index,
                        end: site_end,
                        text: slice(body, index, site_end),
                    });
                    copied_to = site_end;
                }
                index = end;
            }
            None => index += 1,
        }
    }
    sites
}

enum PatternMatch {
    NonCode(usize),
    Site(usize),
}

struct Scanner<'a> {
    body: &'a [char],
    backtick_identifiers: bool,
    python: PythonText,
}

impl Scanner<'_> {
    fn at(&self, index: usize) -> Option<char> {
        self.body.get(index).copied()
    }

    /// The combined scan pattern at `index`: non-code alternatives first, then sites.
    fn pattern_match(&self, index: usize) -> Option<PatternMatch> {
        let body = self.body;
        match self.at(index)? {
            '-' if self.at(index + 1) == Some('-') => {
                let end = (index + 2..body.len())
                    .find(|position| body[*position] == '\n')
                    .map_or(body.len(), |position| position + 1);
                return Some(PatternMatch::NonCode(end));
            }
            '/' if self.at(index + 1) == Some('*') => {
                let end = find(body, "*/", index + 2).map_or(body.len(), |position| position + 2);
                return Some(PatternMatch::NonCode(end));
            }
            quote @ ('\'' | '"') => {
                if let Some(end) = self.backslash_quoted_end(index, quote) {
                    return Some(PatternMatch::NonCode(end));
                }
            }
            '$' => {
                if let Some(end) = self.dollar_quote_end(index) {
                    return Some(PatternMatch::NonCode(end));
                }
            }
            '`' if self.backtick_identifiers => {
                let mut position = index + 1;
                while position < body.len() {
                    if body[position] == '`' {
                        if self.at(position + 1) == Some('`') {
                            position += 2;
                            continue;
                        }
                        return Some(PatternMatch::NonCode(position + 1));
                    }
                    position += 1;
                }
                return Some(PatternMatch::NonCode(body.len()));
            }
            _ => {}
        }
        self.site_pattern_end(index).map(PatternMatch::Site)
    }

    /// `'(?:\\.|''|[^'\\])*(?:'|\Z)` with the regex's backtracking: a backslash before a line
    /// break stops the greedy scan, and the match then ends at the last doubled quote.
    fn backslash_quoted_end(&self, index: usize, quote: char) -> Option<usize> {
        let body = self.body;
        let mut position = index + 1;
        let mut last_doubled: Option<usize> = None;
        loop {
            match self.at(position) {
                None => return Some(body.len()),
                Some('\\') => match self.at(position + 1) {
                    Some(next) if next != '\n' => position += 2,
                    _ => return last_doubled.map(|doubled| doubled + 1),
                },
                Some(character) if character == quote => {
                    if self.at(position + 1) == Some(quote) {
                        last_doubled = Some(position);
                        position += 2;
                        continue;
                    }
                    return Some(position + 1);
                }
                Some(_) => position += 1,
            }
        }
    }

    /// `(?<![A-Za-z0-9_$\x80-\U0010ffff])\$tag\$(?:[\s\S]*?\$tag\$|[\s\S]*\Z)` at `index`.
    fn dollar_quote_end(&self, index: usize) -> Option<usize> {
        if index > 0 {
            let previous = self.body[index - 1];
            if previous.is_ascii_alphanumeric()
                || matches!(previous, '_' | '$')
                || !previous.is_ascii()
            {
                return None;
            }
        }
        let mut position = index + 1;
        if self
            .at(position)
            .is_some_and(|character| character.is_ascii_alphabetic() || character == '_')
        {
            position += 1;
            while self
                .at(position)
                .is_some_and(|character| character.is_ascii_alphanumeric() || character == '_')
            {
                position += 1;
            }
        }
        if self.at(position) != Some('$') {
            return None;
        }
        let delimiter = slice(self.body, index, position + 1);
        Some(
            find(self.body, &delimiter, position + 1)
                .map_or(self.body.len(), |close| close + delimiter.chars().count()),
        )
    }

    /// `(?P<site>@@|\$\{|@|(?:functions)\()` at `index`.
    fn site_pattern_end(&self, index: usize) -> Option<usize> {
        let body = self.body;
        if starts_with(body, index, "@@") {
            return Some(index + 2);
        }
        if starts_with(body, index, "${") {
            return Some(index + 2);
        }
        if self.at(index) == Some('@') {
            return Some(index + 1);
        }
        REFERENCE_FUNCTIONS.iter().find_map(|name| {
            let length = name.chars().count();
            (starts_with(body, index, name) && self.at(index + length) == Some('('))
                .then_some(index + length + 1)
        })
    }

    /// `_interpolation_site_end`.
    fn site_end(&self, start: usize) -> Option<usize> {
        let character = self.at(start)?;
        if character == '@' {
            if starts_with(self.body, start, "@@") {
                return Some(self.interpolation_name_end(start + 2));
            }
            return self.macro_site_end(start);
        }
        if character == '$' {
            return find(self.body, "}", start + 2).map(|end| end + 1);
        }
        if character == '_' {
            let name = slice(self.body, start, self.identifier_end(start)).to_lowercase();
            if FUNCTION_NAMES.contains(&name.as_str()) {
                return self.function_site_end(start);
            }
        }
        None
    }

    fn function_site_end(&self, start: usize) -> Option<usize> {
        let mut name_end = self.identifier_end(start);
        while self.at(name_end).is_some_and(is_python_space) {
            name_end += 1;
        }
        if self.at(name_end) != Some('(') {
            return None;
        }
        self.matching_paren_end(name_end)
    }

    fn macro_site_end(&self, start: usize) -> Option<usize> {
        let name_start = start + 1;
        let first = self.at(name_start)?;
        if first == '\'' {
            return find(self.body, "'", name_start + 1).map(|closing| closing + 1);
        }
        if !(is_python_alpha(self.python, first) || first == '_') {
            return None;
        }
        let name_end = self.identifier_end(name_start);
        if self.at(name_end) != Some('(') {
            return Some(name_end);
        }
        self.matching_paren_end(name_end)
    }

    fn matching_paren_end(&self, opening: usize) -> Option<usize> {
        let body = self.body;
        let mut depth: i64 = 0;
        let mut index = opening;
        let mut quote: Option<char> = None;
        while index < body.len() {
            if quote.is_none() && starts_with(body, index, "--") {
                index = find(body, "\n", index + 2).map_or(body.len(), |newline| newline + 1);
                continue;
            }
            if quote.is_none() && starts_with(body, index, "/*") {
                index = find(body, "*/", index + 2).map_or(body.len(), |end| end + 2);
                continue;
            }
            if quote.is_none()
                && body[index] == '$'
                && let Some(end) = self.dollar_quote_end(index)
            {
                index = end;
                continue;
            }
            let character = body[index];
            if let Some(open) = quote {
                if character == '\\' && matches!(open, '\'' | '"') && index + 1 < body.len() {
                    index += 2;
                    continue;
                }
                if character == open {
                    if self.at(index + 1) == Some(open) {
                        index += 2;
                        continue;
                    }
                    quote = None;
                }
                index += 1;
                continue;
            }
            if matches!(character, '\'' | '"') || (self.backtick_identifiers && character == '`') {
                quote = Some(character);
                index += 1;
                continue;
            }
            if character == '(' {
                depth += 1;
            }
            if character == ')' {
                depth -= 1;
                if depth == 0 {
                    return Some(index + 1);
                }
            }
            index += 1;
        }
        None
    }

    fn interpolation_name_end(&self, start: usize) -> usize {
        let mut index = start;
        while self.at(index).is_some_and(|character| {
            is_python_alnum(self.python, character) || INTERPOLATION_NAME_EXTRA.contains(&character)
        }) {
            index += 1;
        }
        index
    }

    fn identifier_end(&self, start: usize) -> usize {
        let mut index = start;
        while self
            .at(index)
            .is_some_and(|character| is_python_alnum(self.python, character) || character == '_')
        {
            index += 1;
        }
        index
    }
}
