//! The first record Python's `csv.reader` returns for a seed file opened with `newline=""`.

use crate::_helpers::reading::decode_failure;
use crate::project_validation::errors::HeaderError;
use crate::project_validation::models::CsvSettings;
use sqlbuild_core::text::main::decode_text::decode_text;

/// The quote character seed loaders use when a seed declares none.
const DEFAULT_QUOTECHAR: char = '"';
/// The size of the chunks `TextIOWrapper` decodes.
const DECODE_CHUNK: usize = 8192;
const UNQUOTED_NEWLINE: &str =
    "new-line character seen in unquoted field - do you need to open the file with newline=''?";

/// The header row, `None` for an empty file, or the error Python raises reading it.
pub(crate) fn csv_header(
    bytes: &[u8],
    settings: &CsvSettings,
    field_limit: usize,
) -> Result<Vec<String>, HeaderError> {
    let dialect: Dialect = Dialect::new(settings, field_limit);
    let settings: &Dialect = &dialect;
    let mut end: usize = bytes.len().min(DECODE_CHUNK);
    loop {
        let text: String = decoded_prefix(bytes, end)?;
        let complete: bool = end == bytes.len();
        match first_record(&text, settings, complete)? {
            Some(record) => return Ok(record),
            None if complete => return Ok(Vec::new()),
            None => end = bytes.len().min(end + DECODE_CHUNK),
        }
    }
}

/// The reader's settings as `csv.reader` receives them; Python has already accepted them.
pub(crate) struct Dialect {
    delimiter: char,
    quotechar: Option<char>,
    escapechar: Option<char>,
    doublequote: bool,
    skipinitialspace: bool,
    field_limit: usize,
}

impl Dialect {
    fn new(settings: &CsvSettings, field_limit: usize) -> Self {
        let single = |value: &Option<String>| -> Option<char> {
            let mut characters = value.as_deref()?.chars();
            match (characters.next(), characters.next()) {
                (Some(character), None) => Some(character),
                _ => None,
            }
        };
        Self {
            delimiter: single(&settings.delimiter).unwrap_or(','),
            quotechar: single(&settings.quotechar),
            escapechar: single(&settings.escapechar),
            doublequote: settings.doublequote.unwrap_or(true),
            skipinitialspace: settings.skipinitialspace.unwrap_or(false),
            field_limit,
        }
    }
}

/// The text of `bytes[..end]`; a multi-byte character cut by `end` waits for the next chunk.
fn decoded_prefix(bytes: &[u8], end: usize) -> Result<String, HeaderError> {
    let prefix: &[u8] = &bytes[..end];
    match std::str::from_utf8(prefix) {
        Ok(text) => Ok(text.to_owned()),
        Err(error) if error.error_len().is_none() && end < bytes.len() => {
            Ok(String::from_utf8_lossy(&prefix[..error.valid_up_to()]).into_owned())
        }
        Err(_) => decode_text(prefix)
            .map_err(|error| HeaderError::Read(decode_failure(prefix.to_vec(), error))),
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum State {
    StartRecord,
    StartField,
    EscapedChar,
    InField,
    InQuotedField,
    EscapeInQuotedField,
    QuoteInQuotedField,
    EatCrnl,
    AfterEscapedCrnl,
}

/// One character, or the end of a line.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Input {
    Char(char),
    Eol,
}

struct Parser<'a> {
    settings: &'a Dialect,
    state: State,
    field: String,
    field_len: usize,
    fields: Vec<String>,
}

impl Parser<'_> {
    fn save_field(&mut self) {
        self.fields.push(std::mem::take(&mut self.field));
        self.field_len = 0;
    }

    fn add(&mut self, character: char) -> Result<(), HeaderError> {
        if self.field_len >= self.settings.field_limit {
            return Err(HeaderError::Csv(format!(
                "field larger than field limit ({})",
                self.settings.field_limit
            )));
        }
        self.field.push(character);
        self.field_len += 1;
        Ok(())
    }

    fn is_quote(&self, character: char) -> bool {
        self.settings.quotechar == Some(character)
    }

    fn is_escape(&self, character: char) -> bool {
        self.settings.escapechar == Some(character)
    }

    fn delimiter(&self) -> char {
        self.settings.delimiter
    }

    /// CPython's `parse_process_char`.
    fn process(&mut self, input: Input) -> Result<(), HeaderError> {
        let newline = |input: Input| matches!(input, Input::Char('\n' | '\r'));
        loop {
            match self.state {
                State::StartRecord => {
                    if input == Input::Eol {
                        return Ok(());
                    }
                    if newline(input) {
                        self.state = State::EatCrnl;
                        return Ok(());
                    }
                    self.state = State::StartField;
                }
                State::StartField => {
                    match input {
                        Input::Eol => {
                            self.save_field();
                            self.state = State::StartRecord;
                        }
                        Input::Char('\n' | '\r') => {
                            self.save_field();
                            self.state = State::EatCrnl;
                        }
                        Input::Char(character) if self.is_quote(character) => {
                            self.state = State::InQuotedField;
                        }
                        Input::Char(character) if self.is_escape(character) => {
                            self.state = State::EscapedChar;
                        }
                        Input::Char(' ') if self.settings.skipinitialspace => {}
                        Input::Char(character) if character == self.delimiter() => {
                            self.save_field();
                        }
                        Input::Char(character) => {
                            self.add(character)?;
                            self.state = State::InField;
                        }
                    }
                    return Ok(());
                }
                State::EscapedChar => {
                    match input {
                        Input::Char(character @ ('\n' | '\r')) => {
                            self.add(character)?;
                            self.state = State::AfterEscapedCrnl;
                        }
                        Input::Eol => {
                            self.add('\n')?;
                            self.state = State::InField;
                        }
                        Input::Char(character) => {
                            self.add(character)?;
                            self.state = State::InField;
                        }
                    }
                    return Ok(());
                }
                State::AfterEscapedCrnl => {
                    if input == Input::Eol {
                        return Ok(());
                    }
                    self.state = State::InField;
                }
                State::InField => {
                    match input {
                        Input::Eol => {
                            self.save_field();
                            self.state = State::StartRecord;
                        }
                        Input::Char('\n' | '\r') => {
                            self.save_field();
                            self.state = State::EatCrnl;
                        }
                        Input::Char(character) if self.is_escape(character) => {
                            self.state = State::EscapedChar;
                        }
                        Input::Char(character) if character == self.delimiter() => {
                            self.save_field();
                            self.state = State::StartField;
                        }
                        Input::Char(character) => self.add(character)?,
                    }
                    return Ok(());
                }
                State::InQuotedField => {
                    match input {
                        Input::Eol => {}
                        Input::Char(character) if self.is_escape(character) => {
                            self.state = State::EscapeInQuotedField;
                        }
                        Input::Char(character) if self.is_quote(character) => {
                            self.state = if self.settings.doublequote {
                                State::QuoteInQuotedField
                            } else {
                                State::InField
                            };
                        }
                        Input::Char(character) => self.add(character)?,
                    }
                    return Ok(());
                }
                State::EscapeInQuotedField => {
                    self.add(match input {
                        Input::Eol => '\n',
                        Input::Char(character) => character,
                    })?;
                    self.state = State::InQuotedField;
                    return Ok(());
                }
                State::QuoteInQuotedField => {
                    match input {
                        Input::Char(character) if self.is_quote(character) => {
                            self.add(character)?;
                            self.state = State::InQuotedField;
                        }
                        Input::Char(character) if character == self.delimiter() => {
                            self.save_field();
                            self.state = State::StartField;
                        }
                        Input::Eol => {
                            self.save_field();
                            self.state = State::StartRecord;
                        }
                        Input::Char('\n' | '\r') => {
                            self.save_field();
                            self.state = State::EatCrnl;
                        }
                        Input::Char(character) => {
                            self.add(character)?;
                            self.state = State::InField;
                        }
                    }
                    return Ok(());
                }
                State::EatCrnl => {
                    return match input {
                        Input::Char('\n' | '\r') => Ok(()),
                        Input::Eol => {
                            self.state = State::StartRecord;
                            Ok(())
                        }
                        Input::Char(_) => Err(HeaderError::Csv(UNQUOTED_NEWLINE.to_owned())),
                    };
                }
            }
        }
    }
}

/// The first record of `text`, or `None` when `text` ends before it (`complete` is false) or is empty.
fn first_record(
    text: &str,
    settings: &Dialect,
    complete: bool,
) -> Result<Option<Vec<String>>, HeaderError> {
    let mut parser: Parser<'_> = Parser {
        settings,
        state: State::StartRecord,
        field: String::new(),
        field_len: 0,
        fields: Vec::new(),
    };
    let mut lines = lines(text).peekable();
    while let Some(line) = lines.next() {
        let terminated: bool = line.ends_with(['\n', '\r']);
        let last: bool = lines.peek().is_none();
        if last && !complete && !terminated_line(line, terminated, text) {
            return Ok(None);
        }
        for character in line.chars() {
            parser.process(Input::Char(character))?;
        }
        parser.process(Input::Eol)?;
        if parser.state == State::StartRecord {
            return Ok(Some(parser.fields));
        }
    }
    if !complete {
        return Ok(None);
    }
    if parser.field_len != 0 || parser.state == State::InQuotedField {
        parser.save_field();
        return Ok(Some(parser.fields));
    }
    Ok(None)
}

/// Non-blank records in `bytes`, at most `limit`; `None` for a prefix ending before `limit`.
pub(crate) fn csv_record_count(
    bytes: &[u8],
    settings: &CsvSettings,
    complete: bool,
    limit: usize,
) -> Result<Option<usize>, HeaderError> {
    let mut dialect: Dialect = Dialect::new(settings, usize::MAX);
    if settings.quotechar.is_none() {
        dialect.quotechar = Some(DEFAULT_QUOTECHAR);
    }
    let text: String = match std::str::from_utf8(bytes) {
        Ok(text) => text.to_owned(),
        Err(error) if error.error_len().is_none() && !complete => {
            String::from_utf8_lossy(&bytes[..error.valid_up_to()]).into_owned()
        }
        Err(_) => decoded_prefix(bytes, bytes.len())?,
    };
    let mut parser: Parser<'_> = Parser {
        settings: &dialect,
        state: State::StartRecord,
        field: String::new(),
        field_len: 0,
        fields: Vec::new(),
    };
    let mut count: usize = 0;
    let mut lines = lines(&text).peekable();
    while let Some(line) = lines.next() {
        let terminated: bool = line.ends_with(['\n', '\r']);
        if lines.peek().is_none() && !complete && !terminated_line(line, terminated, &text) {
            return Ok(None);
        }
        for character in line.chars() {
            parser.process(Input::Char(character))?;
        }
        parser.process(Input::Eol)?;
        if parser.state == State::StartRecord {
            if !std::mem::take(&mut parser.fields).is_empty() {
                count += 1;
            }
            if count >= limit {
                return Ok(Some(count));
            }
        }
    }
    if !complete {
        return Ok(None);
    }
    if parser.field_len != 0 || parser.state == State::InQuotedField || !parser.fields.is_empty() {
        count += 1;
    }
    Ok(Some(count.min(limit)))
}

/// Whether a final line is known to be whole: it ends with `\n`, or `\r` not followed later.
fn terminated_line(line: &str, terminated: bool, text: &str) -> bool {
    terminated && (line.ends_with('\n') || !text.ends_with('\r'))
}

/// The lines of `text` as `newline=""` iteration yields them, terminators included.
fn lines(text: &str) -> impl Iterator<Item = &str> {
    let mut rest: &str = text;
    std::iter::from_fn(move || {
        if rest.is_empty() {
            return None;
        }
        let bytes: &[u8] = rest.as_bytes();
        let mut end: usize = bytes.len();
        for (index, byte) in bytes.iter().enumerate() {
            if *byte == b'\n' {
                end = index + 1;
                break;
            }
            if *byte == b'\r' {
                end = if bytes.get(index + 1) == Some(&b'\n') {
                    index + 2
                } else {
                    index + 1
                };
                break;
            }
        }
        let (line, tail) = rest.split_at(end);
        rest = tail;
        Some(line)
    })
}
