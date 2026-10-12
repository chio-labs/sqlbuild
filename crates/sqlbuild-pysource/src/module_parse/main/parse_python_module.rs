use ruff_python_ast::ModModule;

/// The module `source` parses to, or the parser's message.
pub fn parse_python_module(source: &str) -> Result<ModModule, String> {
    ruff_python_parser::parse_module(source)
        .map(ruff_python_parser::Parsed::into_syntax)
        .map_err(|error| error.to_string())
}
