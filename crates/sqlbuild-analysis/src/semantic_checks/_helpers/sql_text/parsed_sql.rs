//! The wheel reads semantic completion makes of model SQL: projection spans and parsed facts.

use std::collections::{HashMap, HashSet};

use polyglot_sql::tokens::TokenType;
use polyglot_sql::{
    ComplexityGuardOptions, Dialect, DialectType, Expression, ExpressionWalk, ParseOptions,
};

use crate::semantic_checks::constants::{
    CLOSE_PARENTHESIS, GENERIC_DIALECT, MAX_FUNCTION_CALL_DEPTH, OPEN_PARENTHESIS,
    PROJECTION_SEPARATOR,
};
use crate::semantic_checks::models::SemanticDeferral;
use crate::semantic_validation::main::normalize::normalize_analysis_sql;
use crate::semantic_validation::models::NormalizationInput;

/// The Polyglot dialect the wheel resolves `name` to, when Polyglot knows the name.
pub(crate) fn polyglot_dialect(name: &str) -> Result<Dialect, SemanticDeferral> {
    name.parse::<DialectType>()
        .map(Dialect::get)
        .map_err(|_| SemanticDeferral::UnsupportedDialect)
}

/// Python's `get_complete_schema_binding_request(...).sql` without placeholders.
pub(crate) fn normalized_sql(
    query_sql: &str,
    dialect: Option<&str>,
) -> Result<String, SemanticDeferral> {
    normalize_analysis_sql(NormalizationInput {
        sql: query_sql.to_owned(),
        dialect: dialect.unwrap_or(GENERIC_DIALECT).to_owned(),
        stubs: HashMap::new(),
        placeholders: HashMap::new(),
    })
    .map_err(|_| SemanticDeferral::UnreadableSql)
}

/// Python's `_projection_spans`: top-level SELECT-list item spans in code points.
pub(crate) fn projection_spans(
    sql: &str,
    dialect: Option<&str>,
) -> Result<Vec<(usize, usize)>, SemanticDeferral> {
    let Some(name) = dialect else {
        return Err(SemanticDeferral::UnsupportedDialect);
    };
    let tokens = polyglot_dialect(name)?
        .tokenize(sql)
        .map_err(|_| SemanticDeferral::UnreadableSql)?;
    let mut depth: i64 = 0;
    let mut start: Option<usize> = None;
    let mut spans: Vec<(usize, usize)> = Vec::new();
    for token in tokens {
        if token.text == OPEN_PARENTHESIS {
            depth += 1;
        } else if token.text == CLOSE_PARENTHESIS {
            depth -= 1;
        } else if depth == 0 {
            match start {
                None if token.token_type == TokenType::Select => start = Some(token.span.end),
                Some(begin) if projection_end(token.token_type) => {
                    spans.push((begin, token.span.start));
                    return Ok(spans);
                }
                Some(begin) if token.text == PROJECTION_SEPARATOR => {
                    spans.push((begin, token.span.start));
                    start = Some(token.span.end);
                }
                _ => {}
            }
        }
    }
    if let Some(begin) = start {
        spans.push((begin, sql.chars().count()));
    }
    Ok(spans)
}

fn projection_end(token_type: TokenType) -> bool {
    matches!(
        token_type,
        TokenType::From
            | TokenType::Where
            | TokenType::GroupBy
            | TokenType::Having
            | TokenType::Qualify
            | TokenType::OrderBy
            | TokenType::Limit
            | TokenType::Union
            | TokenType::Intersect
            | TokenType::Except
    )
}

/// The facts `input_aliases` and `unaliased_output_columns` read from one parsed model.
#[derive(Debug, Default)]
pub(crate) struct ParsedModelFacts {
    pub(crate) aliases: HashMap<String, String>,
    pub(crate) unaliased_outputs: HashSet<String>,
}

/// Python's `_parsed_model` facts; SQL the wheel cannot parse has none.
pub(crate) fn parsed_model_facts(
    query_sql: &str,
    dialect: Option<&str>,
) -> Result<ParsedModelFacts, SemanticDeferral> {
    let Some(parsed) = parsed_model(query_sql, dialect)? else {
        return Ok(ParsedModelFacts::default());
    };
    Ok(ParsedModelFacts {
        aliases: input_aliases(&parsed),
        unaliased_outputs: unaliased_outputs(&parsed),
    })
}

/// The wheel's guarded `parse_one` of normalized model SQL; None where it raises.
pub(crate) fn parsed_model(
    query_sql: &str,
    dialect: Option<&str>,
) -> Result<Option<Expression>, SemanticDeferral> {
    let sql = normalized_sql(query_sql, dialect)?;
    let parser = polyglot_dialect(dialect.unwrap_or(GENERIC_DIALECT))?;
    let guard: ComplexityGuardOptions = serde_json::from_value(serde_json::json!({
        "maxFunctionCallDepth": MAX_FUNCTION_CALL_DEPTH,
    }))
    .map_err(|_| SemanticDeferral::NativeFailure)?;
    let options = ParseOptions {
        complexity_guard: Some(guard),
    };
    let Ok(mut statements) = parser.parse_with_options(&sql, &options) else {
        return Ok(None);
    };
    if statements.len() != 1 {
        return Ok(None);
    }
    Ok(Some(statements.remove(0)))
}

fn input_aliases(parsed: &Expression) -> HashMap<String, String> {
    let mut aliases: HashMap<String, HashSet<String>> = HashMap::new();
    for node in parsed.dfs().skip(1) {
        let Expression::Table(table) = node else {
            continue;
        };
        let name = table.name.name.clone();
        aliases
            .entry(name.clone())
            .or_default()
            .insert(name.clone());
        if let Some(alias) = &table.alias {
            aliases.entry(alias.name.clone()).or_default().insert(name);
        }
    }
    let mut unique: HashMap<String, String> = HashMap::new();
    for (alias, names) in aliases {
        let mut names = names.into_iter();
        if let (Some(name), None) = (names.next(), names.next()) {
            unique.insert(alias, name);
        }
    }
    unique
}

fn unaliased_outputs(parsed: &Expression) -> HashSet<String> {
    let Expression::Select(select) = parsed else {
        return HashSet::new();
    };
    let mut outputs: HashSet<String> = HashSet::new();
    for expression in &select.expressions {
        if let Expression::Column(column) = expression {
            outputs.insert(column.name.name.clone());
        }
    }
    outputs
}
