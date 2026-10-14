/// The code points in one run of Unicode decimal digits, valued 0 to 9.
pub(crate) const DIGITS_PER_RUN: u32 = 10;

/// The information separators Python's `str.isspace` accepts and `char::is_whitespace` does not.
pub(crate) const PYTHON_SEPARATOR_CONTROLS: std::ops::RangeInclusive<char> = '\u{1c}'..='\u{1f}';

/// `textwrap`'s em-dash is at least this many hyphens.
pub(crate) const MINIMUM_EM_DASH: usize = 2;

/// The tab stop `str.expandtabs` uses by default.
pub(crate) const TAB_SIZE: usize = 8;
