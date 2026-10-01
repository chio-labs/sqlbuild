//! Positional context of one authored token among its neighbours.

use polyglot_sql::tokens::{Token, TokenType};

use polyglot_sql::DialectType;

use crate::sql_tokens::_helpers::builtin_functions::is_builtin_function;
use crate::sql_tokens::constants::{
    AFTER_AS_KEYWORDS, ALWAYS_KEYWORDS, OPERAND_FOLLOWER_KEYWORDS, OPERAND_FOLLOWERS,
    OPERAND_INTRODUCERS, RANGE_PREDICATE, RELATION_INTRODUCERS, RELATION_POSITION_KEYWORDS,
};
use crate::sql_tokens::main::is_unquoted_word::is_unquoted_word;

pub(crate) struct TokenContext<'a> {
    pub(crate) raws: &'a [String],
    pub(crate) uppers: &'a [String],
    pub(crate) tokens: &'a [Token],
    pub(crate) index: usize,
}

impl TokenContext<'_> {
    /// Whether the token is a keyword in keyword position or a built-in function name.
    pub(crate) fn is_foldable(&self, dialect: DialectType) -> bool {
        if !is_unquoted_word(&self.raws[self.index]) || self.qualified() {
            return false;
        }
        let upper = self.uppers[self.index].as_str();
        if self.previous() == Some("AS") && !AFTER_AS_KEYWORDS.contains(&upper) {
            return false;
        }
        if matches!(
            self.tokens[self.index].token_type,
            TokenType::Var | TokenType::Identifier
        ) {
            return self.next() == Some("(") && is_builtin_function(dialect, upper);
        }
        if ALWAYS_KEYWORDS.contains(&upper) {
            return true;
        }
        if self
            .previous()
            .is_some_and(|previous| RELATION_INTRODUCERS.contains(&previous))
            && !RELATION_POSITION_KEYWORDS.contains(&upper)
        {
            return false;
        }
        if self.continues_phrase() {
            return true;
        }
        if self.next() == Some(RANGE_PREDICATE) {
            return !self.starts_operand();
        }
        !self.next().is_none_or(|next| {
            OPERAND_FOLLOWERS.contains(&next) || OPERAND_FOLLOWER_KEYWORDS.contains(&next)
        })
    }

    /// Words joined to a qualifier by `.`, path keys after `:`, and cast types after `::`.
    fn qualified(&self) -> bool {
        matches!(self.previous(), Some("." | ":" | "::")) || self.next() == Some(".")
    }

    /// A keyword-typed word directly after a keyword that does not introduce an operand.
    fn continues_phrase(&self) -> bool {
        let Some(previous) = self.index.checked_sub(1) else {
            return false;
        };
        is_unquoted_word(&self.raws[previous])
            && !matches!(
                self.tokens[previous].token_type,
                TokenType::Var | TokenType::Identifier
            )
            && !OPERAND_INTRODUCERS.contains(&self.uppers[previous].as_str())
    }

    /// Whether the word sits where an operand starts: after an introducing keyword or bracket.
    fn starts_operand(&self) -> bool {
        self.previous().is_none_or(|previous| {
            matches!(previous, "(" | ",") || OPERAND_INTRODUCERS.contains(&previous)
        })
    }

    fn previous(&self) -> Option<&str> {
        self.index
            .checked_sub(1)
            .map(|previous| self.uppers[previous].as_str())
    }

    fn next(&self) -> Option<&str> {
        self.uppers.get(self.index + 1).map(String::as_str)
    }
}
