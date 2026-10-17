//! Closed token productions for test-planning facts; unrecognized input uses the full parser.

use std::collections::HashSet;

use polyglot_sql::Dialect;
use polyglot_sql::parser::NO_PAREN_FUNCTION_NAMES;
use polyglot_sql::tokens::{Token, TokenType};

use crate::compiler::_helpers::sql_tests::constants::{
    MAX_TEMPLATE_DEPTH, SIMPLE_TEMPLATE_DIALECTS,
};
use crate::compiler::_helpers::sql_tests::planning::{AnalysisTemplate, DBT_REF_FUNCTION};
use crate::compiler::_helpers::sql_tests::relation_markers::MarkerCall;

/// Recognize bounded DuckDB/Snowflake productions; other syntax retains the existing parser.
pub(crate) fn simple_analysis_template(
    sql: &str,
    dialect_name: &str,
    dialect: &Dialect,
) -> Option<AnalysisTemplate> {
    if !SIMPLE_TEMPLATE_DIALECTS.contains(&dialect_name) || sql.contains("/*") {
        return None;
    }
    let tokens = match dialect.tokenize(sql) {
        Ok(tokens) => tokens,
        Err(_) => return None,
    };
    let mut reader = TemplateReader {
        tokens: &tokens,
        position: 0,
    };
    let facts = reader.query(0)?;
    reader.take(TokenType::Semicolon);
    if reader.position != tokens.len() {
        return None;
    }
    Some(AnalysisTemplate {
        existing_cte_names: facts.names,
        marker_calls: facts.calls.into(),
    })
}

struct QueryFacts {
    names: HashSet<String>,
    calls: Vec<MarkerCall>,
}

struct TemplateReader<'a> {
    tokens: &'a [Token],
    position: usize,
}

impl<'a> TemplateReader<'a> {
    fn take(&mut self, kind: TokenType) -> bool {
        if self
            .tokens
            .get(self.position)
            .is_some_and(|token| token.token_type == kind)
        {
            self.position += 1;
            true
        } else {
            false
        }
    }

    fn require(&mut self, kind: TokenType) -> Option<()> {
        self.take(kind).then_some(())
    }

    fn identifier(&mut self) -> Option<&'a str> {
        let token = self.tokens.get(self.position)?;
        if !matches!(
            token.token_type,
            TokenType::Var | TokenType::Identifier | TokenType::QuotedIdentifier | TokenType::Final
        ) {
            return None;
        }
        self.position += 1;
        Some(&token.text)
    }

    fn query(&mut self, depth: usize) -> Option<QueryFacts> {
        if depth > MAX_TEMPLATE_DEPTH {
            return None;
        }
        let mut names: HashSet<String> = HashSet::new();
        let mut cte_calls: Vec<MarkerCall> = Vec::new();
        let has_with = self.take(TokenType::With);
        if has_with {
            loop {
                names.insert(self.identifier()?.to_owned());
                self.require(TokenType::As)?;
                self.require(TokenType::LParen)?;
                cte_calls.extend(self.query(depth + 1)?.calls);
                self.require(TokenType::RParen)?;
                if !self.take(TokenType::Comma) {
                    break;
                }
            }
        }
        let mut calls = self.select(depth)?;
        while self.take(TokenType::Union) {
            if has_with {
                return None;
            }
            self.require(TokenType::All)?;
            if self.take(TokenType::By) {
                let name = self.tokens.get(self.position)?;
                if name.token_type != TokenType::Var || !name.text.eq_ignore_ascii_case("name") {
                    return None;
                }
                self.position += 1;
            }
            calls.extend(self.select(depth)?);
        }
        calls.extend(cte_calls);
        Some(QueryFacts { names, calls })
    }

    fn select(&mut self, depth: usize) -> Option<Vec<MarkerCall>> {
        self.require(TokenType::Select)?;
        loop {
            if !self.take(TokenType::Star) {
                self.scalar(depth + 1)?;
                if self.take(TokenType::As) {
                    self.identifier()?;
                }
            }
            if !self.take(TokenType::Comma) {
                break;
            }
        }
        self.require(TokenType::From)?;
        let mut calls: Vec<MarkerCall> = self.relation()?.into_iter().collect();
        loop {
            let left = self.take(TokenType::Left);
            if !self.take(TokenType::Join) {
                if left {
                    return None;
                }
                break;
            }
            calls.extend(self.relation()?);
            self.require(TokenType::On)?;
            self.condition(depth + 1)?;
        }
        if self.take(TokenType::Where) {
            self.condition(depth + 1)?;
        }
        Some(calls)
    }

    fn relation(&mut self) -> Option<Option<MarkerCall>> {
        let name = self.identifier()?;
        let call = if self.take(TokenType::LParen) {
            let function = name.to_ascii_lowercase();
            if !matches!(
                function.as_str(),
                "__ref" | "__source" | "__seed" | "__dbt_ref"
            ) {
                return None;
            }
            let mut target = self.marker_argument()?.to_owned();
            if function == DBT_REF_FUNCTION && self.take(TokenType::Comma) {
                target.push_str("__");
                target.push_str(self.marker_argument()?);
            }
            self.require(TokenType::RParen)?;
            Some((function, target))
        } else {
            None
        };
        if self.take(TokenType::As) {
            self.identifier()?;
        }
        Some(call)
    }

    /// Require quoted Columns; unquoted arguments can invoke private dialect-specific function rules.
    fn marker_argument(&mut self) -> Option<&'a str> {
        let token = self.tokens.get(self.position)?;
        if token.token_type != TokenType::QuotedIdentifier
            || NO_PAREN_FUNCTION_NAMES.contains(token.text.to_ascii_uppercase().as_str())
        {
            return None;
        }
        self.identifier()
    }

    fn condition(&mut self, depth: usize) -> Option<()> {
        self.scalar(depth)?;
        self.require(TokenType::Eq)?;
        self.scalar(depth)
    }

    fn scalar(&mut self, depth: usize) -> Option<()> {
        self.atom(depth)?;
        while self.take(TokenType::Plus)
            || self.take(TokenType::Dash)
            || self.take(TokenType::Star)
            || self.take(TokenType::Slash)
        {
            self.atom(depth)?;
        }
        Some(())
    }

    fn atom(&mut self, depth: usize) -> Option<()> {
        if depth > MAX_TEMPLATE_DEPTH {
            return None;
        }
        if self.take(TokenType::LParen) {
            self.scalar(depth + 1)?;
            return self.require(TokenType::RParen);
        }
        if self.take(TokenType::Cast) {
            self.require(TokenType::LParen)?;
            self.scalar(depth + 1)?;
            self.require(TokenType::As)?;
            let data_type = self.tokens.get(self.position)?;
            if !matches!(
                data_type.token_type,
                TokenType::Var | TokenType::Int | TokenType::Double
            ) || !["int", "integer", "double"]
                .iter()
                .any(|name| data_type.text.eq_ignore_ascii_case(name))
            {
                return None;
            }
            self.position += 1;
            return self.require(TokenType::RParen);
        }
        if let Some(token) = self.tokens.get(self.position)
            && token.token_type == TokenType::Number
        {
            if !token.text.bytes().any(|byte| byte.is_ascii_digit())
                || !token
                    .text
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || byte == b'.')
                || token.text.bytes().filter(|byte| *byte == b'.').count() > 1
            {
                return None;
            }
            self.position += 1;
            return Some(());
        }
        let name = self.identifier()?;
        if self.take(TokenType::LParen) {
            if !name.eq_ignore_ascii_case("coalesce") {
                return None;
            }
            self.scalar(depth + 1)?;
            while self.take(TokenType::Comma) {
                self.scalar(depth + 1)?;
            }
            self.require(TokenType::RParen)
        } else {
            if self.take(TokenType::Dot) {
                self.identifier()?;
            }
            Some(())
        }
    }
}
