//! Regexes that match as Python's `re` does for this lane's patterns.
//!
//! Python's `\w`, `\d` and `\s` follow `str.isalnum()`, `str.isdecimal()` and `str.isspace()` of
//! the running Python, and `re.IGNORECASE` also matches `ı`, `İ`, `ſ` and the Kelvin sign to ASCII
//! letters; the `regex` crate differs on each beyond ASCII. Patterns spell those classes out.

use std::fmt::Write;
use std::sync::LazyLock;

use regex::Regex;
use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::models::PythonText;

/// `(template token, class)`: Python's `\w`, `\d`, `\s` and an ignore-case identifier start.
static CLASSES: LazyLock<[(&'static str, String); 4]> = LazyLock::new(|| {
    let python: PythonText = active_python_text();
    [
        ("{W}", ranges_class("_", python.alnum_ranges())),
        ("{D}", ranges_class("", python.decimal_ranges())),
        (
            "{S}",
            String::from(
                r"[\t-\r\x{1c}-\x{20}\x{85}\x{a0}\x{1680}\x{2000}-\x{200a}\x{2028}\x{2029}\x{202f}\x{205f}\x{3000}]",
            ),
        ),
        (
            "{L}",
            String::from(r"[A-Za-z_\x{130}\x{131}\x{17f}\x{212a}]"),
        ),
    ]
});

fn ranges_class(extra: &str, ranges: &[(u32, u32)]) -> String {
    let mut class: String = format!("[{extra}");
    for (start, end) in ranges {
        let _ = write!(class, r"\x{{{start:x}}}-\x{{{end:x}}}");
    }
    class.push(']');
    class
}

/// The characters `re.IGNORECASE` matches to one ASCII letter, as a class.
fn ignorecase_letter(letter: char) -> String {
    let extra: &str = match letter.to_ascii_lowercase() {
        'i' => r"\x{130}\x{131}",
        'k' => r"\x{212a}",
        's' => r"\x{17f}",
        _ => "",
    };
    format!(
        "[{}{}{extra}]",
        letter.to_ascii_lowercase(),
        letter.to_ascii_uppercase()
    )
}

/// Python's `re.IGNORECASE` match of an ASCII word, as a sequence of classes.
pub(crate) fn ignorecase_word(word: &str) -> String {
    word.chars().map(ignorecase_letter).collect()
}

/// Whether `character` matches the ASCII letter `letter` under Python's `re.IGNORECASE`.
pub(crate) fn ignorecase_equal(character: char, letter: char) -> bool {
    character.eq_ignore_ascii_case(&letter)
        || matches!(
            (letter.to_ascii_lowercase(), character),
            ('i', '\u{130}' | '\u{131}') | ('k', '\u{212a}') | ('s', '\u{17f}')
        )
}

/// Compile a pattern template, replacing `{W}`, `{D}`, `{S}` and `{L}` with Python's classes.
pub(crate) fn python_regex(template: &str) -> Result<Regex, String> {
    let mut pattern: String = template.to_owned();
    for (token, class) in CLASSES.iter() {
        pattern = pattern.replace(token, class);
    }
    Regex::new(&pattern).map_err(|error| error.to_string())
}
