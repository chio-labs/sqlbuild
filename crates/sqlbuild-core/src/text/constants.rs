/// The code points in one run of Unicode decimal digits, valued 0 to 9.
pub(crate) const DIGITS_PER_RUN: u32 = 10;

/// The information separators Python's `str.isspace` accepts and `char::is_whitespace` does not.
pub(crate) const PYTHON_SEPARATOR_CONTROLS: std::ops::RangeInclusive<char> = '\u{1c}'..='\u{1f}';
