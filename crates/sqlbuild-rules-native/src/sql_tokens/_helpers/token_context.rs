//! Positional context of one authored token among its neighbours.

use polyglot_sql::DialectType;

use crate::sql_tokens::_helpers::builtin_functions::is_builtin_function;
use crate::sql_tokens::_helpers::reserved_keywords::is_reserved_keyword;
use crate::sql_tokens::constants::CALL_OPENER;
use crate::sql_tokens::main::is_unquoted_word::is_unquoted_word;

pub(crate) struct TokenContext<'a> {
    pub(crate) raws: &'a [String],
    pub(crate) uppers: &'a [String],
    pub(crate) index: usize,
}

impl TokenContext<'_> {
    /// Whether the token is a reserved keyword or a built-in function name at a call site.
    pub(crate) fn is_foldable(&self, dialect: DialectType) -> bool {
        if !is_unquoted_word(&self.raws[self.index]) {
            return false;
        }
        let upper = self.uppers[self.index].as_str();
        is_reserved_keyword(dialect, upper)
            || (self.next() == Some(CALL_OPENER) && is_builtin_function(dialect, upper))
    }

    fn next(&self) -> Option<&str> {
        self.uppers.get(self.index + 1).map(String::as_str)
    }
}
