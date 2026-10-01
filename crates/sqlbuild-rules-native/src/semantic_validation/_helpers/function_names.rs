//! Built-in function spellings checked against the spellings the target dialect accepts.

use crate::semantic_validation::models::FunctionProbes;
use crate::semantic_validation::types::ProbeKey;
use crate::sql_scan::main::non_code_end::non_code_end;
use crate::sql_scan::main::skip_whitespace::skip_whitespace;
use crate::sql_scan::models::{QuotePolicy, Unclosed};
use polyglot_sql::{Dialect, DialectType, Expression, ValidationError};
use polyglot_sql_function_catalogs::{CatalogSink, FunctionNameCase, FunctionSignature};
use std::collections::{HashMap, HashSet};
use std::mem::Discriminant;
use std::sync::{LazyLock, OnceLock, PoisonError};

const UNKNOWN_FUNCTION: &str = "B101";
const SNOWFLAKE_FUNCTIONS: &str = include_str!("../../../function_names/snowflake.txt");
const DUCKDB_CATALOG: &str = "duckdb";
const PROBE_PREFIX: &str = "SELECT ";
const TYPE_POSITION_KEYWORD: &str = "AS";
const PROBE_ARITIES: usize = 9;
/// Keywords that may precede a parenthesis without being a function call.
const NON_CALL_KEYWORDS: &str = "ALL AND ANY AS ASOF AT BEFORE BETWEEN BY CASE CHANGES CONNECT CUBE \
    DEFINE DISTINCT DISTINCTROW ELSE END EXCEPT EXCLUDE EXISTS FILTER FROM HAVING ILIKE IN \
    INTERSECT INTERVAL IS JOIN LATERAL LIKE MATCH_CONDITION MATCH_RECOGNIZE MEASURES MINUS NOT ON \
    OR OVER PARTITION PATTERN PERCENT PIVOT PRIOR QUALIFY RANGE RENAME ROLLUP ROW ROWS SAMPLE \
    SELECT SETS SOME TABLE TABLESAMPLE THEN UNION UNPIVOT USING VALUES WHEN WHERE WITH WITHIN";

type SpellingIndex = HashMap<Signature, Vec<String>>;

static KEYWORDS: LazyLock<HashSet<&'static str>> =
    LazyLock::new(|| NON_CALL_KEYWORDS.split_whitespace().collect());
static SNOWFLAKE: LazyLock<HashSet<String>> = LazyLock::new(|| accepted_names(SNOWFLAKE_FUNCTIONS));
static DUCKDB: LazyLock<HashSet<String>> = LazyLock::new(|| {
    let mut sink: CatalogNames = CatalogNames::default();
    polyglot_sql_function_catalogs::register_enabled_catalogs(&mut sink);
    sink.names
});
static SNOWFLAKE_INDEX: [OnceLock<SpellingIndex>; PROBE_ARITIES] =
    [const { OnceLock::new() }; PROBE_ARITIES];
static DUCKDB_INDEX: [OnceLock<SpellingIndex>; PROBE_ARITIES] =
    [const { OnceLock::new() }; PROBE_ARITIES];

/// One call site whose authored built-in spelling the dialect does not accept.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct UnsupportedCall {
    pub(crate) name: String,
    pub(crate) start: usize,
    pub(crate) end: usize,
    pub(crate) suggestion: String,
}

/// How the parser represents one probe call.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
enum Signature {
    /// A generic function node with this upper-case name.
    Named(String),
    /// A typed built-in node, identified by its expression variant.
    Typed(Discriminant<Expression>),
}

/// Upper-case DuckDB names from the SQL library's introspected function catalogue.
#[derive(Default)]
struct CatalogNames {
    names: HashSet<String>,
}

/// Incremental byte-to-character position, so locating every call stays linear in the SQL.
struct Cursor {
    byte: usize,
    characters: usize,
    line: usize,
    column: usize,
}

impl CatalogSink for CatalogNames {
    fn set_dialect_name_case(&mut self, _dialect: &'static str, _name_case: FunctionNameCase) {}

    fn set_function_name_case(
        &mut self,
        _dialect: &'static str,
        _function_name: &str,
        _name_case: FunctionNameCase,
    ) {
    }

    fn register(
        &mut self,
        dialect: &'static str,
        function_name: &str,
        _signatures: Vec<FunctionSignature>,
    ) {
        if dialect == DUCKDB_CATALOG && is_identifier(function_name) {
            self.names.insert(function_name.to_ascii_uppercase());
        }
    }
}

impl Cursor {
    fn new() -> Self {
        Self {
            byte: 0,
            characters: 0,
            line: 1,
            column: 1,
        }
    }

    fn advance(&mut self, sql: &str, byte: usize) {
        for character in sql[self.byte..byte].chars() {
            self.characters += 1;
            if character == '\n' {
                self.line += 1;
                self.column = 1;
            } else {
                self.column += 1;
            }
        }
        self.byte = byte;
    }
}

impl FunctionProbes {
    /// Return the accepted spelling for an unaccepted call-site name the parser treats as built-in.
    fn suggestion(&self, dialect: DialectType, upper: &str, arity: usize) -> Option<String> {
        let key: ProbeKey = (dialect, upper.to_owned(), arity.min(PROBE_ARITIES - 1));
        if let Some(cached) = self
            .suggestions
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .get(&key)
        {
            return cached.clone();
        }
        let found: Option<String> = closest_spelling(dialect, upper, key.2);
        self.suggestions
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .insert(key, found.clone());
        found
    }
}

fn accepted_names(source: &str) -> HashSet<String> {
    source
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .map(str::to_ascii_uppercase)
        .collect()
}

fn accepted(dialect: DialectType) -> Option<&'static HashSet<String>> {
    match dialect {
        DialectType::Snowflake => Some(&SNOWFLAKE),
        DialectType::DuckDB => Some(&DUCKDB),
        _ => None,
    }
}

/// Return located B101 diagnostics, with character spans, for unsupported built-in spellings.
pub(crate) fn unsupported_function_errors(
    sql: &str,
    dialect: DialectType,
    probes: &FunctionProbes,
) -> Vec<ValidationError> {
    let mut cursor: Cursor = Cursor::new();
    unsupported_calls(sql, dialect, probes)
        .into_iter()
        .map(|call| {
            let message: String = format!(
                "Unknown function '{}' for dialect {dialect:?}; did you mean {}?",
                call.name, call.suggestion
            );
            cursor.advance(sql, call.start);
            let start: usize = cursor.characters;
            let end: usize = start + sql[call.start..call.end].chars().count();
            ValidationError::error(message, UNKNOWN_FUNCTION)
                .with_location(cursor.line, cursor.column)
                .with_span(Some(start), Some(end))
        })
        .collect()
}

/// Return call sites in `sql` whose built-in spelling `dialect` does not accept.
pub(crate) fn unsupported_calls(
    sql: &str,
    dialect: DialectType,
    probes: &FunctionProbes,
) -> Vec<UnsupportedCall> {
    let Some(names) = accepted(dialect) else {
        return Vec::new();
    };
    let bytes: &[u8] = sql.as_bytes();
    let mut calls: Vec<UnsupportedCall> = Vec::new();
    let mut index: usize = 0;
    let mut previous_word: Option<(usize, usize)> = None;
    let mut previous_byte: Option<u8> = None;
    while index < bytes.len() {
        match non_code_end(bytes, index, QuotePolicy::COMPILER) {
            Ok(Some(end)) => {
                previous_word = None;
                previous_byte = Some(bytes[index]);
                index = end;
                continue;
            }
            Ok(None) => {}
            Err(Unclosed::BlockComment | Unclosed::Quote | Unclosed::Parenthesis) => break,
        }
        let byte: u8 = bytes[index];
        if byte.is_ascii_whitespace() {
            index += 1;
            continue;
        }
        if !(byte.is_ascii_alphabetic() || byte == b'_') {
            previous_word = None;
            previous_byte = Some(byte);
            index += 1;
            continue;
        }
        let start: usize = index;
        while index < bytes.len() && is_word_byte(bytes[index]) {
            index += 1;
        }
        let name: &str = &sql[start..index];
        let open: usize = skip_whitespace(sql, index);
        let after_qualifier: bool = matches!(previous_byte, Some(b'.' | b'@' | b':'));
        let type_position: bool = previous_word
            .is_some_and(|(from, to)| sql[from..to].eq_ignore_ascii_case(TYPE_POSITION_KEYWORD));
        if bytes.get(open) == Some(&b'(')
            && !after_qualifier
            && !type_position
            && !name.starts_with("__")
            && let upper = name.to_ascii_uppercase()
            && !names.contains(&upper)
            && !KEYWORDS.contains(upper.as_str())
            && let Some(arity) = arity(bytes, open)
            && let Some(suggestion) = probes.suggestion(dialect, &upper, arity)
        {
            calls.push(UnsupportedCall {
                name: name.to_owned(),
                start,
                end: index,
                suggestion,
            });
        }
        previous_word = Some((start, index));
        previous_byte = None;
    }
    calls
}

fn is_word_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'$'
}

fn is_identifier(name: &str) -> bool {
    name.bytes()
        .next()
        .is_some_and(|byte| byte.is_ascii_alphabetic() || byte == b'_')
        && name.bytes().all(is_word_byte)
}

/// Count the top-level arguments of the call whose parenthesis opens at `open`.
fn arity(sql: &[u8], open: usize) -> Option<usize> {
    let mut depth: usize = 0;
    let mut commas: usize = 0;
    let mut empty: bool = true;
    let mut index: usize = open;
    while index < sql.len() {
        match non_code_end(sql, index, QuotePolicy::COMPILER) {
            Ok(Some(end)) => {
                empty = false;
                index = end;
                continue;
            }
            Ok(None) => {}
            Err(Unclosed::BlockComment | Unclosed::Quote | Unclosed::Parenthesis) => return None,
        }
        match sql[index] {
            b'(' | b'[' | b'{' => depth += 1,
            b')' | b']' | b'}' => {
                depth = depth.checked_sub(1)?;
                if depth == 0 {
                    return Some(if empty { 0 } else { commas + 1 });
                }
            }
            b',' if depth == 1 => commas += 1,
            byte if !byte.is_ascii_whitespace() => empty = false,
            _ => {}
        }
        index += 1;
    }
    None
}

/// Return the closest accepted spelling the parser maps to the same built-in node as `upper`.
fn closest_spelling(dialect: DialectType, upper: &str, arity: usize) -> Option<String> {
    let signature: Signature = parsed_signature(dialect, upper, arity)?;
    if signature == Signature::Named(upper.to_owned()) {
        return None;
    }
    spelling_index(dialect, arity)?
        .get(&signature)?
        .iter()
        .min_by_key(|accepted| (edit_distance(upper, accepted), (*accepted).clone()))
        .cloned()
}

fn spelling_index(dialect: DialectType, arity: usize) -> Option<&'static SpellingIndex> {
    let (names, indexes) = match dialect {
        DialectType::Snowflake => (&*SNOWFLAKE, &SNOWFLAKE_INDEX),
        DialectType::DuckDB => (&*DUCKDB, &DUCKDB_INDEX),
        _ => return None,
    };
    Some(indexes.get(arity)?.get_or_init(|| {
        let mut index: SpellingIndex = HashMap::new();
        for name in names {
            if let Some(signature) = parsed_signature(dialect, name, arity) {
                index.entry(signature).or_default().push(name.clone());
            }
        }
        index
    }))
}

fn parsed_signature(dialect: DialectType, upper: &str, arity: usize) -> Option<Signature> {
    let arguments: Vec<String> = (1..=arity).map(|index| format!("a{index}")).collect();
    let sql: String = format!("{PROBE_PREFIX}{upper}({})", arguments.join(", "));
    let Ok(statements) = Dialect::get(dialect).parse(&sql) else {
        return None;
    };
    let [Expression::Select(select)] = statements.as_slice() else {
        return None;
    };
    let [expression] = select.expressions.as_slice() else {
        return None;
    };
    match expression {
        Expression::Function(function) => {
            Some(Signature::Named(function.name.to_ascii_uppercase()))
        }
        Expression::AggregateFunction(function) => {
            Some(Signature::Named(function.name.to_ascii_uppercase()))
        }
        Expression::Column(_)
        | Expression::Identifier(_)
        | Expression::Tuple(_)
        | Expression::Paren(_) => None,
        other => Some(Signature::Typed(std::mem::discriminant(other))),
    }
}

fn edit_distance(left: &str, right: &str) -> usize {
    let right: Vec<char> = right.chars().collect();
    let mut previous: Vec<usize> = (0..=right.len()).collect();
    for (row, left_char) in left.chars().enumerate() {
        let mut current: Vec<usize> = vec![row + 1; right.len() + 1];
        for (column, right_char) in right.iter().enumerate() {
            let substitution: usize = previous[column] + usize::from(left_char != *right_char);
            current[column + 1] = substitution
                .min(previous[column + 1] + 1)
                .min(current[column] + 1);
        }
        previous = current;
    }
    previous[right.len()]
}
