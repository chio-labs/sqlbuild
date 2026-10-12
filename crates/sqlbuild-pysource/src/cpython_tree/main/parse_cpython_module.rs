//! Parse a module the way CPython's `ast.parse` accepts a `str` source.

use ruff_python_ast::PythonVersion;
use ruff_python_parser::{Mode, ParseOptions, Parsed};

use crate::cpython_tree::_helpers::lines::source_lines;
use crate::cpython_tree::constants::BYTE_ORDER_MARK;
use crate::cpython_tree::models::ParsedSource;

/// `source` parsed for the `(major, minor)` Python with CPython's newline translation, if valid.
pub(crate) fn parse_cpython_module(source: &str, python_version: (u8, u8)) -> Option<ParsedSource> {
    if source.starts_with(BYTE_ORDER_MARK) {
        return None;
    }
    let translated: String = source.replace("\r\n", "\n").replace('\r', "\n");
    let (major, minor) = python_version;
    let options: ParseOptions =
        ParseOptions::from(Mode::Module).with_target_version(PythonVersion { major, minor });
    let parsed: Parsed<_> = ruff_python_parser::parse_unchecked(&translated, options);
    if !parsed.has_no_syntax_errors() {
        return None;
    }
    let module = parsed.try_into_module()?.into_syntax();
    Some(ParsedSource {
        module,
        lines: source_lines(&translated),
    })
}
