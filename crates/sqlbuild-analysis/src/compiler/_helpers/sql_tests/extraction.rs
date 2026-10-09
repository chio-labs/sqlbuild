//! Batched extraction and classification of SQL tests before and after expansion.

use std::collections::{HashMap, HashSet, VecDeque};

use serde::{Deserialize, Serialize};

use crate::compiler::_helpers::sql_tests::authored_macro_calls::calls_macro;
use crate::compiler::_helpers::sql_tests::reference_calls::body_calls;
use crate::constants::{
    DIRECT_DEPENDENCY_PATH_LENGTH, MACRO_TEST_MODE, OPERAND_KEYWORDS, OPERATOR_CHARACTERS,
    SELECT_STAR_PROJECTION, TABLE_FUNCTION_TEST_MODE, UDF_TEST_MODE, VALUE_KEYWORDS,
};
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::main::python_strip::python_strip;
use sqlbuild_sqltext::sql_scan::main::dialect_matching_paren::dialect_matching_paren;
use sqlbuild_sqltext::sql_scan::main::dialect_non_code_end::dialect_non_code_end;
use sqlbuild_sqltext::sql_scan::models::{LexicalSyntax, Unclosed};

const MODEL_PREFIXES: [&str; 8] = [
    "__macro__",
    "__ref__",
    "__source__",
    "__seed__",
    "__dbt_ref__",
    "__table_fn__",
    "__expected__",
    "__assert__",
];
const DIRECT_NAMES: [(&str, &str, &str); 3] = [
    (MACRO_TEST_MODE, "__macro_actual__", "__macro_expected__"),
    (UDF_TEST_MODE, "__udf_actual__", "__udf_expected__"),
    (
        TABLE_FUNCTION_TEST_MODE,
        "__table_fn_actual__",
        "__table_fn_expected__",
    ),
];
const DECLARATION_CALLS: [&str; 4] = ["enum", "const", "var", "param"];
/// Longest projection the alias help repeats verbatim.
const ALIAS_HELP_EXPRESSION_LIMIT: usize = 80;
const RESERVED_NAMES: [&str; 5] = [
    "__actual",
    "__expected__typed",
    "__actual__projected",
    "__missing__",
    "__unexpected__",
];

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct BatchRequest {
    tests: Vec<TestRequest>,
    /// The adapter's lexical rules; generic SQL when absent.
    #[serde(default)]
    syntax: Option<LexicalSyntax>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct TestRequest {
    sql: String,
    file_label: String,
    mode: String,
    /// The test before macro and variable expansion, where macro calls are still authored.
    #[serde(default)]
    raw: bool,
    /// Read only the CTE names and body offsets of the authored block, before any expansion.
    #[serde(default)]
    authored: bool,
}

/// One extraction error, with help and the offending text where the author can act on it.
#[derive(Debug, PartialEq, Eq)]
pub(crate) struct Failure {
    pub(crate) message: String,
    pub(crate) help: Option<String>,
    /// The authored text the error is about and its code-point offset in the test SQL.
    pub(crate) token: Option<(String, usize)>,
}

impl From<String> for Failure {
    fn from(message: String) -> Self {
        Self {
            message,
            help: None,
            token: None,
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ErrorResponse {
    index: usize,
    message: String,
    help: Option<String>,
    token: Option<String>,
    token_offset: Option<usize>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
enum BatchResponse {
    Tests(Vec<Classified>),
    Error(ErrorResponse),
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct Cte(pub(crate) String, pub(crate) String);

#[derive(Debug, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum Classified {
    /// Each CTE's name, its code-point offset in the authored block and its stripped body.
    Authored { ctes: Vec<(String, usize, String)> },
    Model {
        mode: String,
        authored: Vec<Cte>,
        #[serde(rename = "macroMocks")]
        macro_mocks: Vec<(String, String)>,
        #[serde(rename = "mockModels")]
        mock_models: Vec<String>,
        #[serde(rename = "mockSources")]
        mock_sources: Vec<String>,
        #[serde(rename = "mockSeeds")]
        mock_seeds: Vec<String>,
        #[serde(rename = "mockDbtRefs")]
        mock_dbt_refs: Vec<String>,
        #[serde(rename = "mockTableFunctions")]
        mock_table_functions: Vec<String>,
        expected: Vec<Cte>,
        #[serde(rename = "expectedModels")]
        expected_models: Vec<String>,
        assertions: Vec<Cte>,
        #[serde(rename = "assertionNames")]
        assertion_names: Vec<String>,
    },
    Direct {
        mode: String,
        helpers: Vec<Cte>,
        actual: Cte,
        expected: Cte,
        /// Whether a helper or the expected CTE has a malformed reference call (P012).
        #[serde(rename = "invalidCalls")]
        invalid_calls: bool,
    },
}

pub(crate) fn extract_batch_json(request_json: &str) -> Result<String, String> {
    let request: BatchRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let syntax = request.syntax.unwrap_or_else(generic_syntax);
    let mut classified = Vec::with_capacity(request.tests.len());
    for (index, test) in request.tests.iter().enumerate() {
        match extract_test(test, &syntax) {
            Ok(test) => classified.push(test),
            Err(failure) => {
                let (token, token_offset) = failure.token.unzip();
                return serde_json::to_string(&BatchResponse::Error(ErrorResponse {
                    index,
                    message: failure.message,
                    help: failure.help,
                    token,
                    token_offset,
                }))
                .map_err(|error| error.to_string());
            }
        }
    }
    serde_json::to_string(&BatchResponse::Tests(classified)).map_err(|error| error.to_string())
}

/// Generic SQL lexical rules: `--` line comments and non-nested block comments.
pub(crate) fn generic_syntax() -> LexicalSyntax {
    LexicalSyntax {
        line_comment_prefixes: vec!["--".to_owned()],
        ..LexicalSyntax::default()
    }
}

/// The test being classified: its file label, the adapter's rules, and whether it is unexpanded.
struct TestScope<'a> {
    file: &'a str,
    syntax: &'a LexicalSyntax,
    raw: bool,
}

fn extract_test(test: &TestRequest, syntax: &LexicalSyntax) -> Result<Classified, Failure> {
    if test.authored {
        return authored_ctes(test, syntax);
    }
    let ctes: Vec<Cte> = scan_ctes(&test.sql, &test.file_label, syntax)?.ctes;
    let scope = TestScope {
        file: &test.file_label,
        syntax,
        raw: test.raw,
    };
    match test.mode.as_str() {
        "model" => classify_model(ctes, &scope),
        "macro" | "udf" | "table_fn" => classify_direct(ctes, &test.mode, &scope),
        mode => Err(format!("SQL test '{}' has unsupported mode '{mode}'", scope.file).into()),
    }
}

/// The authored block's CTEs, or the located error of a CTE name; other errors read as no CTEs.
fn authored_ctes(test: &TestRequest, syntax: &LexicalSyntax) -> Result<Classified, Failure> {
    match scan_ctes(&test.sql, &test.file_label, syntax) {
        Ok(scanned) => Ok(Classified::Authored {
            ctes: scanned
                .ctes
                .into_iter()
                .zip(scanned.body_starts)
                .map(|(cte, start)| (cte.0, start, cte.1))
                .collect(),
        }),
        Err(failure) if failure.token.is_some() => Err(failure),
        Err(_) => Ok(Classified::Authored { ctes: Vec::new() }),
    }
}

/// The top-level CTEs of one test, with the code-point offset of each stripped body.
struct ScannedCtes {
    ctes: Vec<Cte>,
    body_starts: Vec<usize>,
}

fn scan_ctes(sql: &str, file: &str, syntax: &LexicalSyntax) -> Result<ScannedCtes, Failure> {
    let mut body_starts: Vec<usize> = Vec::new();
    let mut index = skip_ignorable(sql, 0, syntax)?;
    index = consume_keyword(sql, index, "WITH").ok_or_else(|| {
        format!("SQL test '{file}' must declare mock CTEs and one __expected__<model> CTE in a top-level WITH clause")
    })?;
    index = skip_ignorable(sql, index, syntax)?;
    if let Some(end) = consume_keyword(sql, index, "RECURSIVE") {
        index = skip_ignorable(sql, end, syntax)?;
    }
    let mut ctes: Vec<Cte> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    loop {
        let (name, end) = read_cte_name(sql, index, file, syntax)?;
        if !seen.insert(name.clone()) {
            return Err(format!("SQL test '{file}' defines duplicate CTE '{name}'").into());
        }
        index = skip_ignorable(sql, end, syntax)?;
        if byte_at(sql, index) == Some(b'(') {
            index = skip_ignorable(
                sql,
                matching_paren(sql, index, "SQL test", syntax)? + 1,
                syntax,
            )?;
        }
        index = consume_keyword(sql, index, "AS")
            .ok_or_else(|| format!("SQL test '{file}' expected keyword AS"))?;
        index = skip_ignorable(sql, index, syntax)?;
        if byte_at(sql, index) != Some(b'(') {
            return Err(format!("SQL test '{file}' CTE '{name}' must use AS (...)").into());
        }
        let close = matching_paren(sql, index, "SQL test", syntax)?;
        let body = &sql[index + 1..close];
        let leading = body.len() - body.trim_start_matches(is_python_space).len();
        body_starts.push(sql[..index + 1 + leading].chars().count());
        ctes.push(Cte(name, python_strip(body).to_owned()));
        index = skip_ignorable(sql, close + 1, syntax)?;
        if byte_at(sql, index) == Some(b',') {
            index = skip_ignorable(sql, index + 1, syntax)?;
        } else {
            break;
        }
    }
    if !statement_ends(sql, index, syntax)? && !ceremonial_select_matches(sql, index, syntax)? {
        return Err(format!(
            "SQL test '{file}' must end after its CTEs; only an optional ceremonial top-level `SELECT 1` may follow them"
        ).into());
    }
    Ok(ScannedCtes { ctes, body_starts })
}

/// Read a top-level CTE name, which must be an unquoted ASCII identifier.
fn read_cte_name(
    sql: &str,
    start: usize,
    file: &str,
    syntax: &LexicalSyntax,
) -> Result<(String, usize), Failure> {
    if let Some(quote) = byte_at(sql, start).filter(|byte| matches!(byte, b'"' | b'`' | b'[')) {
        let end = if quote == b'[' {
            sql[start..]
                .find(']')
                .map_or(sql.len(), |offset| start + offset + 1)
        } else {
            skip_non_code(sql, start, syntax)?
        };
        return Err(cte_name_failure(sql, start, end, file));
    }
    let Some(first) = char_at(sql, start).filter(|first| *first == '_' || first.is_alphabetic())
    else {
        return Err(format!("SQL test '{file}' expected a CTE name").into());
    };
    let mut end = start + first.len_utf8();
    while let Some(character) =
        char_at(sql, end).filter(|character| is_identifier_continue(*character))
    {
        end += character.len_utf8();
    }
    if sql[start..end]
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
    {
        return Ok((sql[start..end].to_owned(), end));
    }
    Err(cte_name_failure(sql, start, end, file))
}

fn cte_name_failure(sql: &str, start: usize, end: usize, file: &str) -> Failure {
    let token = &sql[start..end];
    let shown = if matches!(byte_at(sql, start), Some(b'"' | b'`' | b'[')) {
        token.to_owned()
    } else {
        format!("'{token}'")
    };
    let mut suggestion: String = token
        .trim_matches(|character| matches!(character, '"' | '`' | '[' | ']'))
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || character == '_' {
                character
            } else {
                '_'
            }
        })
        .collect();
    if !suggestion
        .chars()
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
    {
        suggestion.insert_str(0, "cte_");
    }
    Failure {
        message: format!(
            "SQL test '{file}' CTE name {shown} must be an unquoted identifier of ASCII letters, digits and underscores"
        ),
        help: Some(format!(
            "rename the CTE, for example {suggestion}; quoted CTE names and names with $ or non-ASCII characters are not supported"
        )),
        token: Some((token.to_owned(), sql[..start].chars().count())),
    }
}

fn classify_model(ctes: Vec<Cte>, scope: &TestScope<'_>) -> Result<Classified, Failure> {
    let (file, syntax) = (scope.file, scope.syntax);
    validate_independence(&ctes, file, syntax)?;
    let mut authored: Vec<Cte> = Vec::new();
    let mut macro_mocks: Vec<(String, String)> = Vec::new();
    let mut mock_models: Vec<String> = Vec::new();
    let mut mock_sources: Vec<String> = Vec::new();
    let mut mock_seeds: Vec<String> = Vec::new();
    let mut mock_dbt_refs: Vec<String> = Vec::new();
    let mut mock_table_functions: Vec<String> = Vec::new();
    let mut expected: Vec<Cte> = Vec::new();
    let mut expected_models: Vec<String> = Vec::new();
    let mut assertions: Vec<Cte> = Vec::new();
    let mut assertion_names: Vec<String> = Vec::new();
    for cte in ctes {
        let name = cte.0.as_str();
        for (direct_mode, actual, expected_name) in DIRECT_NAMES {
            if name == actual || name == expected_name {
                let label = direct_test_label(direct_mode);
                return Err(format!(
                    "SQL test '{file}' is mode 'model' but defines {label} CTE '{name}'; use TEST (mode {direct_mode})"
                )
                .into());
            }
        }
        if let Some(value) = name.strip_prefix("__macro__") {
            require_suffix(value, "__macro__<macro>", file)?;
            macro_mocks.push((value.to_owned(), macro_mock_value(&cte, file, syntax)?));
        } else if let Some(value) = name.strip_prefix("__ref__") {
            mock_models.push(required(value, "__ref__<model>", file)?);
            authored.push(cte);
        } else if let Some(value) = name.strip_prefix("__source__") {
            mock_sources.push(required(value, "__source__<source>", file)?);
            authored.push(cte);
        } else if let Some(value) = name.strip_prefix("__seed__") {
            mock_seeds.push(required(value, "__seed__<seed>", file)?);
            authored.push(cte);
        } else if let Some(value) = name.strip_prefix("__dbt_ref__") {
            mock_dbt_refs.push(required(
                value,
                "__dbt_ref__<model> or __dbt_ref__<package>__<model>",
                file,
            )?);
            authored.push(cte);
        } else if let Some(value) = name.strip_prefix("__table_fn__") {
            mock_table_functions.push(required(value, "__table_fn__<function>", file)?);
            authored.push(cte);
        } else if let Some(value) = name.strip_prefix("__expected__") {
            expected_models.push(required(value, "__expected__<model>", file)?);
            let label = cte.0.clone();
            validate_expected(&cte, &label, true, scope)?;
            expected.push(cte);
        } else if let Some(value) = name.strip_prefix("__assert__") {
            assertion_names.push(required(value, "__assert__<assertion>", file)?);
            assertions.push(cte);
        } else {
            if RESERVED_NAMES.contains(&name) {
                return Err(
                    format!("SQL test '{file}' uses reserved helper CTE name '{name}'").into(),
                );
            }
            authored.push(cte);
        }
    }
    if mock_models.is_empty()
        && mock_sources.is_empty()
        && mock_seeds.is_empty()
        && mock_dbt_refs.is_empty()
        && mock_table_functions.is_empty()
    {
        return Err(format!(
            "SQL test '{file}' must define at least one __ref__*, __source__*, __seed__*, __dbt_ref__*, or __table_fn__* mock CTE"
        )
        .into());
    }
    if expected_models.is_empty() && assertion_names.is_empty() {
        return Err(format!(
            "SQL test '{file}' must define at least one __expected__<model> or __assert__<assertion> CTE"
        )
        .into());
    }
    Ok(Classified::Model {
        mode: "model".to_owned(),
        authored,
        macro_mocks,
        mock_models,
        mock_sources,
        mock_seeds,
        mock_dbt_refs,
        mock_table_functions,
        expected,
        expected_models,
        assertions,
        assertion_names,
    })
}

/// The label error messages use for one direct-logic mode's CTEs.
fn direct_test_label(mode: &str) -> &'static str {
    match mode {
        MACRO_TEST_MODE => "macro-test",
        UDF_TEST_MODE => "UDF-test",
        _ => "table_fn-test",
    }
}

fn classify_direct(
    ctes: Vec<Cte>,
    mode: &str,
    scope: &TestScope<'_>,
) -> Result<Classified, Failure> {
    let file = scope.file;
    let (_, actual_name, expected_name) = DIRECT_NAMES
        .iter()
        .find(|entry| entry.0 == mode)
        .copied()
        .ok_or_else(|| format!("SQL test '{file}' has unsupported mode '{mode}'"))?;
    let mut helpers: Vec<Cte> = Vec::new();
    let mut actual = None;
    let mut expected = None;
    for cte in ctes {
        if cte.0 == actual_name {
            if actual.is_some() {
                return Err(direct_count_error(file, mode, actual_name, expected_name).into());
            }
            actual = Some(cte);
        } else if cte.0 == expected_name {
            if expected.is_some() {
                return Err(direct_count_error(file, mode, actual_name, expected_name).into());
            }
            validate_expected(&cte, expected_name, false, scope)?;
            expected = Some(cte);
        } else {
            if is_model_name(&cte.0) {
                return Err(format!(
                    "SQL test '{file}' is mode '{mode}' but defines model-test CTE '{}'",
                    cte.0
                )
                .into());
            }
            if let Some(foreign) = DIRECT_NAMES
                .iter()
                .find(|entry| cte.0 == entry.1 || cte.0 == entry.2)
            {
                let kind = if mode == TABLE_FUNCTION_TEST_MODE {
                    "another direct-logic"
                } else {
                    direct_test_label(foreign.0)
                };
                return Err(format!(
                    "SQL test '{file}' is mode '{mode}' but defines {kind} CTE '{}'",
                    cte.0
                )
                .into());
            }
            if RESERVED_NAMES.contains(&cte.0.as_str()) {
                return Err(format!(
                    "SQL test '{file}' uses reserved helper CTE name '{}'",
                    cte.0
                )
                .into());
            }
            helpers.push(cte);
        }
    }
    let actual =
        actual.ok_or_else(|| direct_count_error(file, mode, actual_name, expected_name))?;
    let expected =
        expected.ok_or_else(|| direct_count_error(file, mode, actual_name, expected_name))?;
    let mut invalid_calls = false;
    for helper in &helpers {
        invalid_calls |= malformed_calls_outside_actual(&LogicValidation {
            sql: &helper.1,
            mode,
            label: &format!("helper CTE '{}'", helper.0),
            helper: true,
            allowed: actual_name,
            scope,
        })?;
    }
    invalid_calls |= malformed_calls_outside_actual(&LogicValidation {
        sql: &expected.1,
        mode,
        label: &format!("CTE {expected_name}"),
        helper: false,
        allowed: actual_name,
        scope,
    })?;
    Ok(Classified::Direct {
        mode: mode.to_owned(),
        helpers,
        actual,
        expected,
        invalid_calls,
    })
}

fn direct_count_error(file: &str, mode: &str, actual: &str, expected: &str) -> String {
    format!(
        "SQL test '{file}' mode '{mode}' must define exactly one {actual} CTE and exactly one {expected} CTE"
    )
}

struct LogicValidation<'a> {
    sql: &'a str,
    mode: &'a str,
    label: &'a str,
    helper: bool,
    allowed: &'a str,
    scope: &'a TestScope<'a>,
}

/// Whether a body outside the actual CTE has malformed reference calls; logic calls are errors.
fn malformed_calls_outside_actual(validation: &LogicValidation<'_>) -> Result<bool, String> {
    let file = validation.scope.file;
    let calls_macros = if validation.scope.raw {
        calls_macro(validation.sql)
    } else {
        !macro_calls(validation.sql, validation.scope.syntax)?.is_empty()
    };
    if calls_macros {
        let suffix = if validation.helper && validation.mode == MACRO_TEST_MODE {
            "; call macros only in __macro_actual__"
        } else {
            ""
        };
        return Err(format!(
            "SQL test '{file}' mode '{}' {} must not call macros{suffix}",
            validation.mode, validation.label
        ));
    }
    let calls = body_calls(validation.sql, validation.scope.syntax)?;
    if let Some(kind) = calls.first_logic_kind {
        return Err(format!(
            "SQL test '{file}' mode '{}' {} must not call {kind}; call reusable logic only in {}",
            validation.mode, validation.label, validation.allowed
        ));
    }
    Ok(calls.invalid)
}

fn is_model_name(name: &str) -> bool {
    MODEL_PREFIXES.iter().any(|prefix| name.starts_with(prefix))
}

fn required(value: &str, label: &str, file: &str) -> Result<String, String> {
    require_suffix(value, label, file)?;
    Ok(value.to_owned())
}

fn require_suffix(value: &str, label: &str, file: &str) -> Result<(), String> {
    if value.is_empty() {
        Err(format!(
            "SQL test '{file}' must use {label} to identify a target"
        ))
    } else {
        Ok(())
    }
}

fn macro_mock_value(cte: &Cte, file: &str, syntax: &LexicalSyntax) -> Result<String, String> {
    let body = cte.1.as_str();
    let mut index = skip_ignorable(body, 0, syntax)?;
    index = consume_keyword(body, index, "SELECT")
        .ok_or_else(|| macro_mock_shape(file, &cte.0, false))?;
    index = skip_ignorable(body, index, syntax)?;
    if byte_at(body, index) != Some(b'\'') {
        return Err(macro_mock_shape(file, &cte.0, false));
    }
    let (value, end) = read_string(body, index)?;
    index = skip_ignorable(body, end, syntax)?;
    if byte_at(body, index) == Some(b';') {
        index = skip_ignorable(body, index + 1, syntax)?;
    }
    if index != body.len() {
        return Err(macro_mock_shape(file, &cte.0, true));
    }
    Ok(value)
}

fn macro_mock_shape(file: &str, name: &str, trailing: bool) -> String {
    if trailing {
        format!(
            "SQL test '{file}' macro mock '{name}' must be a single SELECT string literal with no FROM, UNION, or additional columns"
        )
    } else {
        format!(
            "SQL test '{file}' macro mock '{name}' must be a single SELECT string literal, for example SELECT '''US'''"
        )
    }
}

fn validate_expected(
    cte: &Cte,
    label: &str,
    allow_empty_fixture: bool,
    scope: &TestScope<'_>,
) -> Result<(), Failure> {
    let (file, syntax) = (scope.file, scope.syntax);
    if allow_empty_fixture && empty_fixture_marker_matches(&cte.1, syntax)? {
        return Ok(());
    }
    if contains_select_star(&cte.1, syntax)? {
        return Err(select_star_error(file, label).into());
    }
    let branches = split_set_operations(&cte.1, syntax)?;
    let mut names: Vec<Vec<String>> = Vec::new();
    for branch in branches {
        names.push(projection_names(branch, file, label, syntax)?);
    }
    if let Some(first) = names.first() {
        for (index, branch) in names.iter().enumerate().skip(1) {
            if branch != first {
                return Err(format!(
                    "SQL test '{file}' must use the same {label} projection names and order in every set-operation branch; branch {} does not match branch 1",
                    index + 1
                )
                .into());
            }
        }
    }
    Ok(())
}

fn select_star_error(file: &str, label: &str) -> String {
    format!("SQL test '{file}' must not use SELECT * in {label} CTEs")
}

pub(crate) fn empty_fixture_marker_matches(
    sql: &str,
    syntax: &LexicalSyntax,
) -> Result<bool, String> {
    let mut index = skip_ignorable(sql, 0, syntax)?;
    let Some(select_end) = consume_keyword(sql, index, "SELECT") else {
        return Ok(false);
    };
    index = skip_ignorable(sql, select_end, syntax)?;
    if byte_at(sql, index) != Some(b'*') {
        return Ok(false);
    }
    index = skip_ignorable(sql, index + 1, syntax)?;
    let Some(from_end) = consume_keyword(sql, index, "FROM") else {
        return Ok(false);
    };
    index = skip_ignorable(sql, from_end, syntax)?;
    let Some((name, name_end)) = read_identifier(sql, index, syntax) else {
        return Ok(false);
    };
    if !name.eq_ignore_ascii_case("__empty_fixture") {
        return Ok(false);
    }
    index = skip_ignorable(sql, name_end, syntax)?;
    if byte_at(sql, index) != Some(b'(') {
        return Ok(false);
    }
    index = skip_ignorable(sql, index + 1, syntax)?;
    if byte_at(sql, index) != Some(b')') {
        return Ok(false);
    }
    index = skip_ignorable(sql, index + 1, syntax)?;
    Ok(index == sql.len())
}

fn projection_names(
    branch: &str,
    file: &str,
    label: &str,
    syntax: &LexicalSyntax,
) -> Result<Vec<String>, Failure> {
    let start = skip_ignorable(branch, 0, syntax)?;
    if byte_at(branch, start) == Some(b'(') {
        return Err(format!(
            "SQL test '{file}' must write each {label} set-operation branch as a plain SELECT without enclosing parentheses"
        )
        .into());
    }
    if consume_keyword(branch, start, "WITH").is_some() {
        return Err(Failure {
            message: format!("SQL test '{file}' must not use WITH inside {label}"),
            help: Some(
                "define the shared rows as a helper CTE in the test's top-level WITH clause and select from it"
                    .to_owned(),
            ),
            token: None,
        });
    }
    let mut select_end = consume_keyword(branch, start, "SELECT").ok_or_else(|| {
        format!("SQL test '{file}' must define each {label} set-operation branch as a SELECT query")
    })?;
    let quantifier = skip_ignorable(branch, select_end, syntax)?;
    if let Some(end) = consume_keyword(branch, quantifier, "DISTINCT")
        .or_else(|| consume_keyword(branch, quantifier, "ALL"))
    {
        select_end = end;
        let on = skip_ignorable(branch, end, syntax)?;
        if let Some(on_end) = consume_keyword(branch, on, "ON") {
            let open = skip_ignorable(branch, on_end, syntax)?;
            if byte_at(branch, open) == Some(b'(') {
                select_end = matching_paren(branch, open, "SQL test", syntax)? + 1;
            }
        }
    }
    let mut end = select_list_from(branch, select_end, syntax)?.unwrap_or(branch.len());
    for keyword in [
        "WHERE", "GROUP", "HAVING", "QUALIFY", "WINDOW", "ORDER", "LIMIT", "OFFSET", "FETCH",
    ] {
        if let Some(position) = find_top_level_clause_keyword(branch, select_end, keyword, syntax)?
        {
            end = end.min(position);
        }
    }
    let expressions = split_top_level(&branch[select_end..end], b',', syntax)?;
    if expressions.is_empty() {
        return Err(
            format!("SQL test '{file}' must project at least one column in {label}").into(),
        );
    }
    expressions
        .into_iter()
        .map(|expression| projection_name(expression, file, label, syntax))
        .collect()
}

/// An `AS` alias, or the name of a bare or qualified column reference; anything else needs `AS`.
fn projection_name(
    expression: &str,
    file: &str,
    label: &str,
    syntax: &LexicalSyntax,
) -> Result<String, Failure> {
    if let Some(position) = find_last_top_level_keyword(expression, "AS", syntax)? {
        let alias_start = skip_ignorable(expression, position + 2, syntax)?;
        if let Some((alias, end)) = read_identifier(expression, alias_start, syntax)
            && skip_ignorable(expression, end, syntax)? == expression.len()
        {
            return Ok(alias);
        }
    }
    let value = python_strip(expression);
    if value == SELECT_STAR_PROJECTION
        || value
            .strip_suffix(SELECT_STAR_PROJECTION)
            .is_some_and(|qualifier| qualifier.trim_end().ends_with('.'))
    {
        return Err(select_star_error(file, label).into());
    }
    if read_identifier(value, 0, syntax).is_some_and(|(_, end)| end == value.len()) {
        return Ok(value.to_owned());
    }
    if let Some(name) = qualified_projection_name(value, syntax)? {
        return Ok(name);
    }
    if let Some(alias) = implicit_alias(value, syntax)? {
        return Ok(alias);
    }
    let shown = if value.chars().count() <= ALIAS_HELP_EXPRESSION_LIMIT && !value.contains('\n') {
        value
    } else {
        "<expression>"
    };
    Err(Failure {
        message: format!("SQL test '{file}' must alias every non-trivial {label} projection"),
        help: Some(format!(
            "name the column with an alias, for example {shown} AS <name>; only a bare or qualified column reference may go unaliased"
        )),
        token: None,
    })
}

/// The implicit alias ending `expression`, unless that last token is an operand or a value keyword.
fn implicit_alias(expression: &str, syntax: &LexicalSyntax) -> Result<Option<String>, String> {
    let Some(alias_start) = last_top_level_token_start(expression, syntax)? else {
        return Ok(None);
    };
    let Some((alias, alias_end)) = read_identifier(expression, alias_start, syntax) else {
        return Ok(None);
    };
    if skip_ignorable(expression, alias_end, syntax)? != expression.len() {
        return Ok(None);
    }
    let quoted = matches!(byte_at(expression, alias_start), Some(b'"' | b'`'));
    if !quoted && is_keyword(&alias, VALUE_KEYWORDS.iter().chain(OPERAND_KEYWORDS)) {
        return Ok(None);
    }
    let Some(prefix) = non_empty_trimmed(&expression[..alias_start], syntax)? else {
        return Ok(None);
    };
    if prefix
        .chars()
        .next_back()
        .is_some_and(|character| OPERATOR_CHARACTERS.contains(character))
    {
        return Ok(None);
    }
    let word_start = prefix
        .char_indices()
        .rev()
        .take_while(|(_, character)| is_identifier_continue(*character))
        .last()
        .map_or(prefix.len(), |(index, _)| index);
    Ok((!is_keyword(&prefix[word_start..], OPERAND_KEYWORDS.iter())).then_some(alias))
}

fn is_keyword<'a>(word: &str, mut keywords: impl Iterator<Item = &'a &'a str>) -> bool {
    keywords.any(|keyword| keyword.eq_ignore_ascii_case(word))
}

/// The start of the last top-level token that follows whitespace or a comment.
fn last_top_level_token_start(
    expression: &str,
    syntax: &LexicalSyntax,
) -> Result<Option<usize>, String> {
    let mut last = None;
    let mut separated = false;
    let mut depth = 0_isize;
    let mut index = 0;
    while index < expression.len() {
        if let Some(end) = comment_end(expression, index, syntax)? {
            separated = true;
            index = end;
            continue;
        }
        if char_at(expression, index).is_some_and(is_python_space) {
            separated = true;
            index += char_len(expression, index);
            continue;
        }
        if separated && depth == 0 {
            last = Some(index);
        }
        separated = false;
        let next = skip_non_code(expression, index, syntax)?;
        if next != index {
            index = next;
            continue;
        }
        match byte_at(expression, index) {
            Some(b'(') => depth += 1,
            Some(b')') => depth -= 1,
            _ => {}
        }
        index += char_len(expression, index);
    }
    Ok(last)
}

fn qualified_projection_name(
    expression: &str,
    syntax: &LexicalSyntax,
) -> Result<Option<String>, String> {
    let Some((mut name, mut end)) = read_identifier(expression, 0, syntax) else {
        return Ok(None);
    };
    let mut qualified = false;
    loop {
        end = skip_ignorable(expression, end, syntax)?;
        if byte_at(expression, end) != Some(b'.') {
            break;
        }
        let part_start = skip_ignorable(expression, end + 1, syntax)?;
        let Some((part, part_end)) = read_identifier(expression, part_start, syntax) else {
            return Ok(None);
        };
        name = part;
        end = part_end;
        qualified = true;
    }
    Ok((qualified && python_strip(&expression[end..]).is_empty()).then_some(name))
}

pub(crate) fn validate_independence(
    ctes: &[Cte],
    file: &str,
    syntax: &LexicalSyntax,
) -> Result<(), String> {
    let names: HashMap<String, String> = ctes
        .iter()
        .map(|cte| (cte.0.to_lowercase(), cte.0.clone()))
        .collect();
    let expected: HashSet<String> = names
        .iter()
        .filter(|(_, name)| name.starts_with("__expected__"))
        .map(|(key, _)| key.clone())
        .collect();
    let assertions: HashSet<String> = names
        .iter()
        .filter(|(_, name)| name.starts_with("__assert__"))
        .map(|(key, _)| key.clone())
        .collect();
    for cte in ctes {
        let (prohibited_prefix, label) = if expected.contains(&cte.0.to_lowercase()) {
            ("__assert__", "assertion")
        } else if assertions.contains(&cte.0.to_lowercase()) {
            ("__expected__", "expected result")
        } else {
            continue;
        };
        if cte.1.to_lowercase().contains(prohibited_prefix)
            && let Some(nested) = nested_cte_names(&cte.1, syntax)?
                .into_iter()
                .find(|name| name.starts_with(prohibited_prefix))
        {
            return Err(format!(
                "SQL test '{file}' check CTE '{}' must not define {label} CTE '{nested}'; expected results and assertions must be independent",
                cte.0
            ));
        }
    }
    if expected.is_empty() || assertions.is_empty() {
        return Ok(());
    }
    let dependencies: HashMap<String, Vec<String>> = ctes
        .iter()
        .map(|cte| {
            let refs = known_relation_names(&cte.1, &names, syntax)
                .unwrap_or_else(|_| known_identifiers(&cte.1, &names));
            (cte.0.to_lowercase(), refs)
        })
        .collect();
    for (origins, prohibited) in [(&expected, &assertions), (&assertions, &expected)] {
        let mut sorted = origins.iter().collect::<Vec<_>>();
        sorted.sort();
        for origin in sorted {
            if let Some(path) = dependency_path(origin, prohibited, &dependencies) {
                let rendered: Vec<&String> = path
                    .iter()
                    .map(|key| {
                        names
                            .get(key)
                            .ok_or_else(|| format!("SQL test '{file}' has an unknown dependency"))
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                let through = if rendered.len() > DIRECT_DEPENDENCY_PATH_LENGTH {
                    format!(
                        " through {}",
                        rendered[1..rendered.len() - 1]
                            .iter()
                            .map(|name| format!("'{name}'"))
                            .collect::<Vec<_>>()
                            .join(" -> ")
                    )
                } else {
                    String::new()
                };
                let target = rendered
                    .last()
                    .ok_or_else(|| format!("SQL test '{file}' has an empty dependency path"))?;
                return Err(format!(
                    "SQL test '{file}' check CTE '{}' must not depend on '{}'{}; expected results and assertions must be independent",
                    rendered[0], target, through
                ));
            }
        }
    }
    Ok(())
}

fn dependency_path(
    origin: &str,
    prohibited: &HashSet<String>,
    dependencies: &HashMap<String, Vec<String>>,
) -> Option<Vec<String>> {
    let mut pending = VecDeque::from([vec![origin.to_owned()]]);
    let mut visited = HashSet::from([origin.to_owned()]);
    while let Some(path) = pending.pop_front() {
        for dependency in dependencies.get(path.last()?).into_iter().flatten() {
            let mut candidate = path.clone();
            candidate.push(dependency.clone());
            if prohibited.contains(dependency) {
                return Some(candidate);
            }
            if visited.insert(dependency.clone()) {
                pending.push_back(candidate);
            }
        }
    }
    None
}

fn nested_cte_names(sql: &str, syntax: &LexicalSyntax) -> Result<Vec<String>, String> {
    let mut names: Vec<String> = Vec::new();
    let mut index = 0;
    while let Some(position) = find_keyword(sql, index, "WITH", syntax)? {
        let mut cursor = skip_ignorable(sql, position + 4, syntax)?;
        while let Some((name, end)) = read_identifier(sql, cursor, syntax) {
            if !names.contains(&name) {
                names.push(name);
            }
            cursor = skip_ignorable(sql, end, syntax)?;
            if byte_at(sql, cursor) == Some(b'(') {
                cursor = skip_ignorable(
                    sql,
                    matching_paren(sql, cursor, "SQL test", syntax)? + 1,
                    syntax,
                )?;
            }
            let Some(as_end) = consume_keyword(sql, cursor, "AS") else {
                break;
            };
            cursor = skip_ignorable(sql, as_end, syntax)?;
            if byte_at(sql, cursor) != Some(b'(') {
                break;
            }
            cursor = skip_ignorable(
                sql,
                matching_paren(sql, cursor, "SQL test", syntax)? + 1,
                syntax,
            )?;
            if byte_at(sql, cursor) != Some(b',') {
                break;
            }
            cursor = skip_ignorable(sql, cursor + 1, syntax)?;
        }
        index = position + 4;
    }
    Ok(names)
}

fn known_relation_names(
    sql: &str,
    names: &HashMap<String, String>,
    syntax: &LexicalSyntax,
) -> Result<Vec<String>, String> {
    let mut refs: Vec<String> = Vec::new();
    let mut index = 0;
    let mut depth = 0_usize;
    let mut from_depths: HashSet<usize> = HashSet::new();
    let mut expected_relation_depths: HashSet<usize> = HashSet::new();
    while index < sql.len() {
        index = skip_ignorable(sql, index, syntax)?;
        if index >= sql.len() {
            break;
        }
        if expected_relation_depths.remove(&depth)
            && let Some((name, end)) = read_identifier(sql, index, syntax)
        {
            let key = name.to_lowercase();
            if names.contains_key(&key) && !refs.contains(&key) {
                refs.push(key);
            }
            index = end;
            continue;
        }

        let next = skip_non_code(sql, index, syntax)?;
        if next != index {
            index = next;
            continue;
        }
        if byte_at(sql, index) == Some(b'(') {
            depth += 1;
            index += 1;
            continue;
        }
        if byte_at(sql, index) == Some(b')') {
            from_depths.remove(&depth);
            expected_relation_depths.remove(&depth);
            depth = depth.saturating_sub(1);
            index += 1;
            continue;
        }
        if consume_keyword(sql, index, "FROM").is_some() {
            from_depths.insert(depth);
            expected_relation_depths.insert(depth);
            index += 4;
            continue;
        }
        if consume_keyword(sql, index, "JOIN").is_some() {
            expected_relation_depths.insert(depth);
            index += 4;
            continue;
        }
        if from_depths.contains(&depth) && byte_at(sql, index) == Some(b',') {
            expected_relation_depths.insert(depth);
            index += 1;
            continue;
        }
        if from_depths.contains(&depth)
            && [
                "WHERE",
                "GROUP",
                "HAVING",
                "QUALIFY",
                "WINDOW",
                "ORDER",
                "LIMIT",
                "OFFSET",
                "FETCH",
                "UNION",
                "EXCEPT",
                "INTERSECT",
            ]
            .into_iter()
            .any(|keyword| consume_keyword(sql, index, keyword).is_some())
        {
            from_depths.remove(&depth);
            expected_relation_depths.remove(&depth);
        }
        index += char_len(sql, index);
    }
    Ok(refs)
}

fn known_identifiers(sql: &str, names: &HashMap<String, String>) -> Vec<String> {
    names
        .keys()
        .filter(|name| sql.to_lowercase().contains(name.as_str()))
        .cloned()
        .collect()
}

fn macro_calls(sql: &str, syntax: &LexicalSyntax) -> Result<Vec<String>, String> {
    let mut calls: Vec<String> = Vec::new();
    let mut index = 0;
    while index < sql.len() {
        index = skip_non_code(sql, index, syntax)?;
        if index >= sql.len() {
            break;
        }
        if byte_at(sql, index) == Some(b'@')
            && let Some((name, end)) = read_identifier(sql, index + 1, syntax)
        {
            let open = space_end(sql, end);
            if byte_at(sql, open) == Some(b'(') && !DECLARATION_CALLS.contains(&name.as_str()) {
                if !calls.contains(&name) {
                    calls.push(name);
                }
                index = matching_paren(sql, open, "SQL macro", syntax)? + 1;
                continue;
            }
        }
        index += char_len(sql, index);
    }
    Ok(calls)
}

/// Whether any `SELECT`, optionally `DISTINCT` or `ALL`, is followed by `*`.
fn contains_select_star(sql: &str, syntax: &LexicalSyntax) -> Result<bool, String> {
    let mut index = 0;
    while let Some(position) = find_keyword(sql, index, "SELECT", syntax)? {
        let mut value = skip_ignorable(sql, position + 6, syntax)?;
        if let Some(end) =
            consume_keyword(sql, value, "DISTINCT").or_else(|| consume_keyword(sql, value, "ALL"))
        {
            value = skip_ignorable(sql, end, syntax)?;
        }
        if byte_at(sql, value) == Some(b'*') {
            return Ok(true);
        }
        index = position + 6;
    }
    Ok(false)
}

/// What a top-level scan does after visiting one code offset.
enum CodeStep<T> {
    Advance,
    Resume(usize),
    Stop(T),
}

/// Visit each code offset outside quotes and comments with its depth after that byte's parenthesis.
fn scan_code<T>(
    sql: &str,
    start: usize,
    syntax: &LexicalSyntax,
    mut visit: impl FnMut(usize, isize) -> Result<CodeStep<T>, String>,
) -> Result<Option<T>, String> {
    let mut index = start;
    let mut depth = 0;
    while index < sql.len() {
        let next = skip_non_code(sql, index, syntax)?;
        if next != index {
            index = next;
            continue;
        }
        match byte_at(sql, index) {
            Some(b'(') => depth += 1,
            Some(b')') => depth -= 1,
            _ => {}
        }
        match visit(index, depth)? {
            CodeStep::Advance => index += char_len(sql, index),
            CodeStep::Resume(resume) => index = resume,
            CodeStep::Stop(value) => return Ok(Some(value)),
        }
    }
    Ok(None)
}

/// Return `value` without surrounding whitespace and comments, or `None` when no code remains.
fn non_empty_trimmed<'a>(
    value: &'a str,
    syntax: &LexicalSyntax,
) -> Result<Option<&'a str>, String> {
    let start = skip_ignorable(value, 0, syntax)?;
    let mut end = start;
    let mut index = start;
    while index < value.len() {
        if let Some(comment) = comment_end(value, index, syntax)? {
            index = comment;
            continue;
        }
        let next = skip_non_code(value, index, syntax)?;
        if next != index {
            end = next;
            index = next;
            continue;
        }
        let width = char_len(value, index);
        if !char_at(value, index).is_some_and(is_python_space) {
            end = index + width;
        }
        index += width;
    }
    Ok(Some(&value[start..end]).filter(|trimmed| !trimmed.is_empty()))
}

/// Split on top-level `UNION`, `INTERSECT` and `EXCEPT`, each with an optional `ALL`/`DISTINCT`.
pub(crate) fn split_set_operations<'a>(
    sql: &'a str,
    syntax: &LexicalSyntax,
) -> Result<Vec<&'a str>, String> {
    let mut values: Vec<&str> = Vec::new();
    let mut start = 0;
    scan_code::<()>(sql, 0, syntax, |index, depth| {
        if depth != 0 {
            return Ok(CodeStep::Advance);
        }
        let Some(end) = set_operator_end(sql, index, syntax)? else {
            return Ok(CodeStep::Advance);
        };
        values.extend(non_empty_trimmed(&sql[start..index], syntax)?);
        let mut resume = skip_ignorable(sql, end, syntax)?;
        if let Some(quantifier_end) =
            consume_keyword(sql, resume, "ALL").or_else(|| consume_keyword(sql, resume, "DISTINCT"))
        {
            resume = skip_ignorable(sql, quantifier_end, syntax)?;
        }
        start = resume;
        Ok(CodeStep::Resume(resume))
    })?;
    values.extend(non_empty_trimmed(&sql[start..], syntax)?);
    Ok(values)
}

/// Return the end of a set operator at `index`; `* EXCEPT (...)` star modifiers are not operators.
fn set_operator_end(
    sql: &str,
    index: usize,
    syntax: &LexicalSyntax,
) -> Result<Option<usize>, String> {
    if let Some(end) =
        consume_keyword(sql, index, "UNION").or_else(|| consume_keyword(sql, index, "INTERSECT"))
    {
        return Ok(Some(end));
    }
    match consume_keyword(sql, index, "EXCEPT") {
        Some(end) if previous_code_byte(sql, index, syntax)? != Some(b'*') => Ok(Some(end)),
        _ => Ok(None),
    }
}

pub(crate) fn split_top_level<'a>(
    sql: &'a str,
    separator: u8,
    syntax: &LexicalSyntax,
) -> Result<Vec<&'a str>, String> {
    let mut values: Vec<&str> = Vec::new();
    let mut start = 0;
    let mut bracket_depth: isize = 0;
    scan_code::<()>(sql, 0, syntax, |index, depth| {
        match byte_at(sql, index) {
            Some(b'[' | b'{') => bracket_depth += 1,
            Some(b']' | b'}') => bracket_depth -= 1,
            Some(byte) if byte == separator && depth == 0 && bracket_depth == 0 => {
                values.extend(non_empty_trimmed(&sql[start..index], syntax)?);
                start = index + 1;
            }
            _ => {}
        }
        Ok(CodeStep::Advance)
    })?;
    values.extend(non_empty_trimmed(&sql[start..], syntax)?);
    Ok(values)
}

pub(crate) fn find_top_level_keyword(
    sql: &str,
    start: usize,
    keyword: &str,
    syntax: &LexicalSyntax,
) -> Result<Option<usize>, String> {
    scan_code(sql, start, syntax, |index, depth| {
        Ok(
            if depth == 0 && consume_keyword(sql, index, keyword).is_some() {
                CodeStep::Stop(index)
            } else {
                CodeStep::Advance
            },
        )
    })
}

/// The top-level `FROM` that ends a select list, skipping the `FROM` of `IS [NOT] DISTINCT FROM`.
fn select_list_from(
    sql: &str,
    start: usize,
    syntax: &LexicalSyntax,
) -> Result<Option<usize>, String> {
    let mut search_start = start;
    while let Some(position) = find_top_level_clause_keyword(sql, search_start, "FROM", syntax)? {
        if !trailing_distinct_operator(&sql[start..position], syntax)? {
            return Ok(Some(position));
        }
        search_start = position + "FROM".len();
    }
    Ok(None)
}

/// Whether `prefix` ends with `IS DISTINCT` or `IS NOT DISTINCT`, ignoring comments.
fn trailing_distinct_operator(prefix: &str, syntax: &LexicalSyntax) -> Result<bool, String> {
    let Some((rest, word)) = trailing_word(prefix, syntax)? else {
        return Ok(false);
    };
    if !word.eq_ignore_ascii_case("DISTINCT") {
        return Ok(false);
    }
    let Some((rest, word)) = trailing_word(rest, syntax)? else {
        return Ok(false);
    };
    if word.eq_ignore_ascii_case("IS") {
        return Ok(true);
    }
    if !word.eq_ignore_ascii_case("NOT") {
        return Ok(false);
    }
    let Some((_, word)) = trailing_word(rest, syntax)? else {
        return Ok(false);
    };
    Ok(word.eq_ignore_ascii_case("IS"))
}

/// The code before the last word of `value` and that word, ignoring trailing comments.
fn trailing_word<'a>(
    value: &'a str,
    syntax: &LexicalSyntax,
) -> Result<Option<(&'a str, &'a str)>, String> {
    let Some(trimmed) = non_empty_trimmed(value, syntax)? else {
        return Ok(None);
    };
    let trimmed_end = trimmed.as_ptr() as usize - value.as_ptr() as usize + trimmed.len();
    let code = &value[..trimmed_end];
    let word_start = code
        .char_indices()
        .rev()
        .take_while(|(_, character)| is_identifier_continue(*character))
        .last()
        .map(|(index, _)| index);
    Ok(word_start.map(|start| (&code[..start], &code[start..])))
}

fn find_top_level_clause_keyword(
    sql: &str,
    start: usize,
    keyword: &str,
    syntax: &LexicalSyntax,
) -> Result<Option<usize>, String> {
    let mut search_start = start;
    while let Some(position) = find_top_level_keyword(sql, search_start, keyword, syntax)? {
        if previous_code_byte(sql, position, syntax)? != Some(b'.') {
            return Ok(Some(position));
        }
        search_start = position + keyword.len();
    }
    Ok(None)
}

fn previous_code_byte(sql: &str, end: usize, syntax: &LexicalSyntax) -> Result<Option<u8>, String> {
    let mut previous = None;
    let mut index = 0;
    while index < end {
        let next = skip_non_code(sql, index, syntax)?;
        if next != index {
            index = next;
            continue;
        }
        let value = byte_at(sql, index);
        if value.is_some_and(|byte| !byte.is_ascii_whitespace()) {
            previous = value;
        }
        index += char_len(sql, index);
    }
    Ok(previous)
}

fn find_last_top_level_keyword(
    sql: &str,
    keyword: &str,
    syntax: &LexicalSyntax,
) -> Result<Option<usize>, String> {
    let mut found = None;
    let mut start = 0;
    while let Some(position) = find_top_level_keyword(sql, start, keyword, syntax)? {
        found = Some(position);
        start = position + keyword.len();
    }
    Ok(found)
}

fn find_keyword(
    sql: &str,
    start: usize,
    keyword: &str,
    syntax: &LexicalSyntax,
) -> Result<Option<usize>, String> {
    let mut index = start;
    while index < sql.len() {
        let next = skip_non_code(sql, index, syntax)?;
        if next != index {
            index = next;
            continue;
        }
        if consume_keyword(sql, index, keyword).is_some() {
            return Ok(Some(index));
        }
        index += char_len(sql, index);
    }
    Ok(None)
}

fn ceremonial_select_matches(
    sql: &str,
    start: usize,
    syntax: &LexicalSyntax,
) -> Result<bool, String> {
    let mut index = skip_ignorable(sql, start, syntax)?;
    let Some(end) = consume_keyword(sql, index, "SELECT") else {
        return Ok(false);
    };
    index = skip_ignorable(sql, end, syntax)?;
    if byte_at(sql, index) != Some(b'1') {
        return Ok(false);
    }
    statement_ends(sql, index + 1, syntax)
}

fn statement_ends(sql: &str, start: usize, syntax: &LexicalSyntax) -> Result<bool, String> {
    let mut index = skip_ignorable(sql, start, syntax)?;
    if byte_at(sql, index) == Some(b';') {
        index = skip_ignorable(sql, index + 1, syntax)?;
    }
    Ok(index == sql.len())
}

/// Match `keyword` ASCII case-insensitively at `start`, outside a longer identifier.
fn consume_keyword(sql: &str, start: usize, keyword: &str) -> Option<usize> {
    let end = start + keyword.len();
    let value = sql.get(start..end)?;
    if !value.eq_ignore_ascii_case(keyword) {
        return None;
    }
    if char_at(sql, end).is_some_and(is_identifier_continue) {
        return None;
    }
    if sql[..start]
        .chars()
        .next_back()
        .is_some_and(is_identifier_continue)
    {
        return None;
    }
    Some(end)
}

/// Read an unquoted identifier, or a quoted one with doubled quotes unescaped.
fn read_identifier(sql: &str, start: usize, syntax: &LexicalSyntax) -> Option<(String, usize)> {
    if let Some(quote) = byte_at(sql, start).filter(|byte| matches!(byte, b'"' | b'`')) {
        let Ok(end) = skip_non_code(sql, start, syntax) else {
            return None;
        };
        let quote_text = char::from(quote).to_string();
        return Some((
            sql.get(start + 1..end - 1)?
                .replace(&format!("{quote_text}{quote_text}"), &quote_text),
            end,
        ));
    }
    let first = char_at(sql, start)?;
    if !is_identifier_start(first) {
        return None;
    }
    let mut end = start + first.len_utf8();
    for character in sql[end..].chars() {
        if !is_identifier_continue(character) {
            break;
        }
        end += character.len_utf8();
    }
    Some((sql[start..end].to_owned(), end))
}

fn is_identifier_start(value: char) -> bool {
    value == '_' || value.is_alphabetic()
}

fn is_identifier_continue(value: char) -> bool {
    is_identifier_start(value) || value.is_numeric() || value == '$'
}

fn byte_at(sql: &str, index: usize) -> Option<u8> {
    sql.as_bytes().get(index).copied()
}

fn char_at(sql: &str, index: usize) -> Option<char> {
    sql.get(index..).and_then(|rest| rest.chars().next())
}

fn char_len(sql: &str, index: usize) -> usize {
    char_at(sql, index).map_or(1, char::len_utf8)
}

/// Skip Python whitespace (`str.isspace`).
fn space_end(sql: &str, mut index: usize) -> usize {
    while let Some(character) = char_at(sql, index).filter(|character| is_python_space(*character))
    {
        index += character.len_utf8();
    }
    index
}

/// The end of a comment starting at `index` under the adapter's rules; quoted text is code here.
fn comment_end(sql: &str, index: usize, syntax: &LexicalSyntax) -> Result<Option<usize>, String> {
    let rest = &sql.as_bytes()[index.min(sql.len())..];
    let starts_comment = rest.starts_with(b"/*")
        || syntax
            .line_comment_prefixes
            .iter()
            .any(|prefix| rest.starts_with(prefix.as_bytes()));
    if !starts_comment {
        return Ok(None);
    }
    dialect_non_code_end(sql.as_bytes(), index, syntax)
        .map_err(|error| scan_error_message(error, "SQL test"))
}

fn skip_ignorable(sql: &str, mut index: usize, syntax: &LexicalSyntax) -> Result<usize, String> {
    loop {
        index = space_end(sql, index);
        match comment_end(sql, index, syntax)? {
            Some(end) => index = end,
            None => return Ok(index),
        }
    }
}

fn skip_non_code(sql: &str, index: usize, syntax: &LexicalSyntax) -> Result<usize, String> {
    if index >= sql.len() {
        return Ok(index);
    }
    Ok(dialect_non_code_end(sql.as_bytes(), index, syntax)
        .map_err(|error| scan_error_message(error, "SQL test"))?
        .unwrap_or(index))
}

fn matching_paren(
    sql: &str,
    open: usize,
    context: &str,
    syntax: &LexicalSyntax,
) -> Result<usize, String> {
    dialect_matching_paren(sql.as_bytes(), open, syntax).map_err(|error| match error {
        Unclosed::Parenthesis => scan_error_message(error, context),
        _ => scan_error_message(error, "SQL test"),
    })
}

fn scan_error_message(error: Unclosed, context: &str) -> String {
    match error {
        Unclosed::BlockComment => "SQL test contains an unclosed block comment".to_owned(),
        Unclosed::Quote => format!("{context} contains an unclosed quoted string"),
        Unclosed::Parenthesis => format!("{context} contains an unclosed parenthesis"),
    }
}

fn read_string(sql: &str, start: usize) -> Result<(String, usize), String> {
    let mut value = String::new();
    let mut index = start + 1;
    while index < sql.len() {
        if byte_at(sql, index) == Some(b'\'') {
            if byte_at(sql, index + 1) == Some(b'\'') {
                value.push('\'');
                index += 2;
            } else {
                return Ok((value, index + 1));
            }
        } else {
            let Some(c) = char_at(sql, index) else {
                break;
            };
            value.push(c);
            index += c.len_utf8();
        }
    }
    Err("SQL test macro mock has an unterminated string literal".to_owned())
}
