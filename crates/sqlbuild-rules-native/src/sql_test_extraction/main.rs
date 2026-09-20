//! Batched extraction and classification of already-expanded SQL tests.

use std::collections::{HashMap, HashSet, VecDeque};

use serde::{Deserialize, Serialize};

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
    ("macro", "__macro_actual__", "__macro_expected__"),
    ("udf", "__udf_actual__", "__udf_expected__"),
    ("table_fn", "__table_fn_actual__", "__table_fn_expected__"),
];
const DECLARATION_CALLS: [&str; 4] = ["enum", "const", "var", "param"];
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
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct TestRequest {
    sql: String,
    file_label: String,
    mode: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
struct Cte(String, String);

#[derive(Debug, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum Classified {
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
    },
}

pub(crate) fn extract_batch_json(request_json: &str) -> Result<String, String> {
    let request: BatchRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let mut classified = Vec::with_capacity(request.tests.len());
    for test in &request.tests {
        let ctes = extract_ctes(&test.sql, &test.file_label)?;
        classified.push(classify(ctes, &test.file_label, &test.mode)?);
    }
    serde_json::to_string(&classified).map_err(|error| error.to_string())
}

fn extract_ctes(sql: &str, file: &str) -> Result<Vec<Cte>, String> {
    let mut index = skip_ignorable(sql, 0)?;
    index = consume_keyword(sql, index, "WITH").ok_or_else(|| {
        format!("SQL test '{file}' must declare mock CTEs and one __expected__<model> CTE before `SELECT 1`")
    })?;
    index = skip_ignorable(sql, index)?;
    if let Some(end) = consume_keyword(sql, index, "RECURSIVE") {
        index = skip_ignorable(sql, end)?;
    }
    let mut ctes = Vec::new();
    let mut seen = HashSet::new();
    loop {
        let (name, end) = read_identifier(sql, index)
            .ok_or_else(|| format!("SQL test '{file}' expected a CTE name"))?;
        if !seen.insert(name.clone()) {
            return Err(format!("SQL test '{file}' defines duplicate CTE '{name}'"));
        }
        index = skip_ignorable(sql, end)?;
        if byte_at(sql, index) == Some(b'(') {
            index = skip_ignorable(sql, matching_paren(sql, index, "SQL test")? + 1)?;
        }
        index = consume_keyword(sql, index, "AS")
            .ok_or_else(|| format!("SQL test '{file}' expected keyword AS"))?;
        index = skip_ignorable(sql, index)?;
        if byte_at(sql, index) != Some(b'(') {
            return Err(format!("SQL test '{file}' CTE '{name}' must use AS (...)"));
        }
        let close = matching_paren(sql, index, "SQL test")?;
        ctes.push(Cte(name, sql[index + 1..close].trim().to_owned()));
        index = skip_ignorable(sql, close + 1)?;
        if byte_at(sql, index) == Some(b',') {
            index = skip_ignorable(sql, index + 1)?;
        } else {
            break;
        }
    }
    if !is_ceremonial_select(sql, index)? {
        return Err(format!(
            "SQL test '{file}' must end with a ceremonial top-level `SELECT 1` after its CTEs"
        ));
    }
    Ok(ctes)
}

fn classify(ctes: Vec<Cte>, file: &str, mode: &str) -> Result<Classified, String> {
    match mode {
        "model" => classify_model(ctes, file),
        "macro" | "udf" | "table_fn" => classify_direct(ctes, file, mode),
        _ => Err(format!("SQL test '{file}' has unsupported mode '{mode}'")),
    }
}

#[allow(clippy::too_many_lines)]
fn classify_model(ctes: Vec<Cte>, file: &str) -> Result<Classified, String> {
    validate_independence(&ctes, file)?;
    let mut authored = Vec::new();
    let mut macro_mocks = Vec::new();
    let mut mock_models = Vec::new();
    let mut mock_sources = Vec::new();
    let mut mock_seeds = Vec::new();
    let mut mock_dbt_refs = Vec::new();
    let mut mock_table_functions = Vec::new();
    let mut expected = Vec::new();
    let mut expected_models = Vec::new();
    let mut assertions = Vec::new();
    let mut assertion_names = Vec::new();
    for cte in ctes {
        let name = cte.0.as_str();
        for (direct_mode, actual, expected_name) in DIRECT_NAMES {
            if name == actual || name == expected_name {
                return Err(format!(
                    "SQL test '{file}' is mode 'model' but defines {direct_mode}-test CTE '{name}'; use TEST (mode {direct_mode})"
                ));
            }
        }
        if let Some(value) = name.strip_prefix("__macro__") {
            require_suffix(value, "__macro__<macro>", file)?;
            macro_mocks.push((value.to_owned(), macro_mock_value(&cte, file)?));
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
            validate_expected(&cte, file, "__expected__<model>")?;
            expected.push(cte);
        } else if let Some(value) = name.strip_prefix("__assert__") {
            assertion_names.push(required(value, "__assert__<assertion>", file)?);
            assertions.push(cte);
        } else {
            if RESERVED_NAMES.contains(&name) {
                return Err(format!(
                    "SQL test '{file}' uses reserved helper CTE name '{name}'"
                ));
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
        ));
    }
    if expected_models.is_empty() && assertion_names.is_empty() {
        return Err(format!(
            "SQL test '{file}' must define at least one __expected__<model> or __assert__<assertion> CTE"
        ));
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

fn classify_direct(ctes: Vec<Cte>, file: &str, mode: &str) -> Result<Classified, String> {
    let (_, actual_name, expected_name) = DIRECT_NAMES
        .iter()
        .find(|entry| entry.0 == mode)
        .copied()
        .expect("known mode");
    let mut helpers = Vec::new();
    let mut actual = None;
    let mut expected = None;
    for cte in ctes {
        if cte.0 == actual_name {
            if actual.is_some() {
                return Err(direct_count_error(file, mode, actual_name, expected_name));
            }
            actual = Some(cte);
        } else if cte.0 == expected_name {
            if expected.is_some() {
                return Err(direct_count_error(file, mode, actual_name, expected_name));
            }
            validate_expected(&cte, file, expected_name)?;
            expected = Some(cte);
        } else {
            if is_model_name(&cte.0) {
                return Err(format!(
                    "SQL test '{file}' is mode '{mode}' but defines model-test CTE '{}'",
                    cte.0
                ));
            }
            if DIRECT_NAMES
                .iter()
                .any(|entry| cte.0 == entry.1 || cte.0 == entry.2)
            {
                let kind = if mode == "table_fn" {
                    "another direct-logic"
                } else if mode == "macro" {
                    if cte.0.starts_with("__udf") {
                        "UDF-test"
                    } else {
                        "table_fn-test"
                    }
                } else if cte.0.starts_with("__macro") {
                    "macro-test"
                } else {
                    "table_fn-test"
                };
                return Err(format!(
                    "SQL test '{file}' is mode '{mode}' but defines {kind} CTE '{}'",
                    cte.0
                ));
            }
            if RESERVED_NAMES.contains(&cte.0.as_str()) {
                return Err(format!(
                    "SQL test '{file}' uses reserved helper CTE name '{}'",
                    cte.0
                ));
            }
            helpers.push(cte);
        }
    }
    let actual =
        actual.ok_or_else(|| direct_count_error(file, mode, actual_name, expected_name))?;
    let expected =
        expected.ok_or_else(|| direct_count_error(file, mode, actual_name, expected_name))?;
    for helper in &helpers {
        validate_no_logic_calls(
            &helper.1,
            file,
            mode,
            &format!("helper CTE '{}'", helper.0),
            actual_name,
        )?;
    }
    validate_no_logic_calls(
        &expected.1,
        file,
        mode,
        &format!("CTE {expected_name}"),
        actual_name,
    )?;
    Ok(Classified::Direct {
        mode: mode.to_owned(),
        helpers,
        actual,
        expected,
    })
}

fn direct_count_error(file: &str, mode: &str, actual: &str, expected: &str) -> String {
    format!(
        "SQL test '{file}' mode '{mode}' must define exactly one {actual} CTE and exactly one {expected} CTE"
    )
}

fn validate_no_logic_calls(
    sql: &str,
    file: &str,
    mode: &str,
    label: &str,
    allowed: &str,
) -> Result<(), String> {
    if !macro_calls(sql)?.is_empty() {
        return Err(format!(
            "SQL test '{file}' mode '{mode}' {label} must not call macros"
        ));
    }
    for (needle, kind) in [("__udf(", "udf"), ("__table_fn(", "table_fn")] {
        if contains_executable(sql, needle)? {
            return Err(format!(
                "SQL test '{file}' mode '{mode}' {label} must not call {kind}; call reusable logic only in {allowed}"
            ));
        }
    }
    Ok(())
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

fn macro_mock_value(cte: &Cte, file: &str) -> Result<String, String> {
    let body = cte.1.as_str();
    let mut index = skip_ignorable(body, 0)?;
    index = consume_keyword(body, index, "SELECT")
        .ok_or_else(|| macro_mock_shape(file, &cte.0, false))?;
    index = skip_ignorable(body, index)?;
    if byte_at(body, index) != Some(b'\'') {
        return Err(macro_mock_shape(file, &cte.0, false));
    }
    let (value, end) = read_string(body, index)?;
    index = skip_ignorable(body, end)?;
    if byte_at(body, index) == Some(b';') {
        index = skip_ignorable(body, index + 1)?;
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

fn validate_expected(cte: &Cte, file: &str, label: &str) -> Result<(), String> {
    if contains_select_star(&cte.1)? {
        return Err(format!(
            "SQL test '{file}' must not use SELECT * in {label} CTEs"
        ));
    }
    let branches = split_unions(&cte.1)?;
    let mut names = Vec::new();
    for branch in branches {
        names.push(projection_names(branch, file)?);
    }
    if let Some(first) = names.first() {
        for (index, branch) in names.iter().enumerate().skip(1) {
            if branch != first {
                return Err(format!(
                    "SQL test '{file}' must use the same __expected__<model> projection names and order in every set-operation branch; branch {} does not match branch 1",
                    index + 1
                ));
            }
        }
    }
    Ok(())
}

fn projection_names(branch: &str, file: &str) -> Result<Vec<String>, String> {
    let start = skip_ignorable(branch, 0)?;
    let select_end = consume_keyword(branch, start, "SELECT").ok_or_else(|| format!("SQL test '{file}' must define each __expected__<model> set-operation branch as a SELECT query"))?;
    let end = find_top_level_keyword(branch, select_end, "FROM")?.unwrap_or(branch.len());
    let expressions = split_top_level(&branch[select_end..end], b',')?;
    if expressions.is_empty() {
        return Err(format!(
            "SQL test '{file}' must project at least one column in __expected__<model>"
        ));
    }
    expressions
        .into_iter()
        .map(|expression| projection_name(expression, file))
        .collect()
}

fn projection_name(expression: &str, file: &str) -> Result<String, String> {
    if let Some(position) = find_last_top_level_keyword(expression, "AS")? {
        let alias_start = skip_ignorable(expression, position + 2)?;
        if let Some((alias, end)) = read_identifier(expression, alias_start)
            && expression[end..].trim().is_empty()
        {
            return Ok(alias);
        }
    }
    let value = expression.trim();
    if read_identifier(value, 0).is_some_and(|(_, end)| end == value.len()) {
        return Ok(value.to_owned());
    }
    if let Some(alias) = implicit_projection_alias(value) {
        return Ok(alias);
    }
    Err(format!(
        "SQL test '{file}' must alias every non-trivial __expected__<model> projection"
    ))
}

fn implicit_projection_alias(expression: &str) -> Option<String> {
    let alias_start = expression.rfind(char::is_whitespace)? + 1;
    let prefix = expression[..alias_start].trim_end();
    if prefix.is_empty()
        || prefix
            .chars()
            .next_back()
            .is_some_and(|character| "+-*/%=<>|&^,".contains(character))
    {
        return None;
    }
    let (alias, end) = read_identifier(expression, alias_start)?;
    (end == expression.len()).then_some(alias)
}

fn validate_independence(ctes: &[Cte], file: &str) -> Result<(), String> {
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
            && let Some(nested) = nested_cte_names(&cte.1)?
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
            let refs = known_relation_names(&cte.1, &names)
                .unwrap_or_else(|_| known_identifiers(&cte.1, &names));
            (cte.0.to_lowercase(), refs)
        })
        .collect();
    for (origins, prohibited) in [(&expected, &assertions), (&assertions, &expected)] {
        let mut sorted = origins.iter().collect::<Vec<_>>();
        sorted.sort();
        for origin in sorted {
            if let Some(path) = dependency_path(origin, prohibited, &dependencies) {
                let rendered = path
                    .iter()
                    .map(|key| names.get(key).expect("known name"))
                    .collect::<Vec<_>>();
                let through = if rendered.len() > 2 {
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
                return Err(format!(
                    "SQL test '{file}' check CTE '{}' must not depend on '{}'{}; expected results and assertions must be independent",
                    rendered[0],
                    rendered.last().expect("path target"),
                    through
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

fn nested_cte_names(sql: &str) -> Result<Vec<String>, String> {
    let mut names = Vec::new();
    let mut index = 0;
    while let Some(position) = find_keyword(sql, index, "WITH")? {
        let mut cursor = skip_ignorable(sql, position + 4)?;
        while let Some((name, end)) = read_identifier(sql, cursor) {
            if !names.contains(&name) {
                names.push(name);
            }
            cursor = skip_ignorable(sql, end)?;
            if byte_at(sql, cursor) == Some(b'(') {
                cursor = skip_ignorable(sql, matching_paren(sql, cursor, "SQL test")? + 1)?;
            }
            let Some(as_end) = consume_keyword(sql, cursor, "AS") else {
                break;
            };
            cursor = skip_ignorable(sql, as_end)?;
            if byte_at(sql, cursor) != Some(b'(') {
                break;
            }
            cursor = skip_ignorable(sql, matching_paren(sql, cursor, "SQL test")? + 1)?;
            if byte_at(sql, cursor) != Some(b',') {
                break;
            }
            cursor = skip_ignorable(sql, cursor + 1)?;
        }
        index = position + 4;
    }
    Ok(names)
}

fn known_relation_names(sql: &str, names: &HashMap<String, String>) -> Result<Vec<String>, String> {
    let mut refs = Vec::new();
    let mut index = 0;
    while index < sql.len() {
        index = skip_non_code(sql, index)?;
        if index >= sql.len() {
            break;
        }
        let keyword = if consume_keyword(sql, index, "FROM").is_some()
            || consume_keyword(sql, index, "JOIN").is_some()
        {
            Some(4)
        } else {
            None
        };
        if let Some(length) = keyword {
            let start = skip_ignorable(sql, index + length)?;
            if let Some((name, _)) = read_identifier(sql, start) {
                let key = name.to_lowercase();
                if names.contains_key(&key) && !refs.contains(&key) {
                    refs.push(key);
                }
            }
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

fn macro_calls(sql: &str) -> Result<Vec<String>, String> {
    let mut calls = Vec::new();
    let mut index = 0;
    while index < sql.len() {
        index = skip_non_code(sql, index)?;
        if index >= sql.len() {
            break;
        }
        if byte_at(sql, index) == Some(b'@')
            && let Some((name, end)) = read_identifier(sql, index + 1)
        {
            let open = skip_whitespace(sql, end);
            if byte_at(sql, open) == Some(b'(') && !DECLARATION_CALLS.contains(&name.as_str()) {
                if !calls.contains(&name) {
                    calls.push(name);
                }
                index = matching_paren(sql, open, "SQL macro")? + 1;
                continue;
            }
        }
        index += char_len(sql, index);
    }
    Ok(calls)
}

fn contains_executable(sql: &str, needle: &str) -> Result<bool, String> {
    let mut index = 0;
    while index < sql.len() {
        index = skip_non_code(sql, index)?;
        if index >= sql.len() {
            break;
        }
        if sql[index..].starts_with(needle) {
            return Ok(true);
        }
        index += char_len(sql, index);
    }
    Ok(false)
}

fn contains_select_star(sql: &str) -> Result<bool, String> {
    let mut index = 0;
    while let Some(position) = find_keyword(sql, index, "SELECT")? {
        let value = skip_ignorable(sql, position + 6)?;
        if byte_at(sql, value) == Some(b'*') {
            return Ok(true);
        }
        index = position + 6;
    }
    Ok(false)
}

fn split_unions(sql: &str) -> Result<Vec<&str>, String> {
    let mut values = Vec::new();
    let mut start = 0;
    let mut index = 0;
    let mut depth = 0;
    while index < sql.len() {
        let next = skip_non_code(sql, index)?;
        if next != index {
            index = next;
            continue;
        }
        match byte_at(sql, index) {
            Some(b'(') => depth += 1,
            Some(b')') => depth -= 1,
            _ => {}
        }
        if depth == 0
            && let Some(end) = consume_keyword(sql, index, "UNION")
        {
            let value = sql[start..index].trim();
            if !value.is_empty() {
                values.push(value);
            }
            index = skip_ignorable(sql, end)?;
            if let Some(all_end) = consume_keyword(sql, index, "ALL") {
                index = skip_ignorable(sql, all_end)?;
            }
            start = index;
            continue;
        }
        index += char_len(sql, index);
    }
    let value = sql[start..].trim();
    if !value.is_empty() {
        values.push(value);
    }
    Ok(values)
}

fn split_top_level(sql: &str, separator: u8) -> Result<Vec<&str>, String> {
    let mut values = Vec::new();
    let mut start = 0;
    let mut index = 0;
    let mut depth = 0;
    while index < sql.len() {
        let next = skip_non_code(sql, index)?;
        if next != index {
            index = next;
            continue;
        }
        match byte_at(sql, index) {
            Some(b'(') => depth += 1,
            Some(b')') => depth -= 1,
            Some(value) if value == separator && depth == 0 => {
                let item = sql[start..index].trim();
                if !item.is_empty() {
                    values.push(item);
                }
                start = index + 1;
            }
            _ => {}
        }
        index += char_len(sql, index);
    }
    let item = sql[start..].trim();
    if !item.is_empty() {
        values.push(item);
    }
    Ok(values)
}

fn find_top_level_keyword(sql: &str, start: usize, keyword: &str) -> Result<Option<usize>, String> {
    let mut index = start;
    let mut depth = 0;
    while index < sql.len() {
        let next = skip_non_code(sql, index)?;
        if next != index {
            index = next;
            continue;
        }
        match byte_at(sql, index) {
            Some(b'(') => depth += 1,
            Some(b')') => depth -= 1,
            _ => {}
        }
        if depth == 0 && consume_keyword(sql, index, keyword).is_some() {
            return Ok(Some(index));
        }
        index += char_len(sql, index);
    }
    Ok(None)
}

fn find_last_top_level_keyword(sql: &str, keyword: &str) -> Result<Option<usize>, String> {
    let mut found = None;
    let mut start = 0;
    while let Some(position) = find_top_level_keyword(sql, start, keyword)? {
        found = Some(position);
        start = position + keyword.len();
    }
    Ok(found)
}
fn find_keyword(sql: &str, start: usize, keyword: &str) -> Result<Option<usize>, String> {
    let mut index = start;
    while index < sql.len() {
        let next = skip_non_code(sql, index)?;
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

fn is_ceremonial_select(sql: &str, start: usize) -> Result<bool, String> {
    let mut index = skip_ignorable(sql, start)?;
    let Some(end) = consume_keyword(sql, index, "SELECT") else {
        return Ok(false);
    };
    index = skip_ignorable(sql, end)?;
    if byte_at(sql, index) != Some(b'1') {
        return Ok(false);
    }
    index = skip_ignorable(sql, index + 1)?;
    if byte_at(sql, index) == Some(b';') {
        index = skip_ignorable(sql, index + 1)?;
    }
    Ok(index == sql.len())
}

fn consume_keyword(sql: &str, start: usize, keyword: &str) -> Option<usize> {
    let end = start + keyword.len();
    let value = sql.get(start..end)?;
    if !value.eq_ignore_ascii_case(keyword) {
        return None;
    }
    if end < sql.len() && is_identifier_continue(sql[end..].chars().next()?) {
        return None;
    }
    if start > 0 && is_identifier_continue(sql[..start].chars().next_back()?) {
        return None;
    }
    Some(end)
}
fn read_identifier(sql: &str, start: usize) -> Option<(String, usize)> {
    if matches!(byte_at(sql, start), Some(b'"') | Some(b'`')) {
        let quote = byte_at(sql, start)?;
        let end = skip_quote(sql, start, "SQL identifier").ok()?;
        let quote_text = char::from(quote).to_string();
        return Some((
            sql[start + 1..end - 1].replace(&format!("{quote_text}{quote_text}"), &quote_text),
            end,
        ));
    }
    let first = sql.get(start..)?.chars().next()?;
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
fn char_len(sql: &str, index: usize) -> usize {
    sql[index..].chars().next().map_or(1, char::len_utf8)
}
fn skip_whitespace(sql: &str, mut index: usize) -> usize {
    while index < sql.len() {
        let Some(c) = sql[index..].chars().next() else {
            break;
        };
        if !c.is_whitespace() {
            break;
        }
        index += c.len_utf8();
    }
    index
}

fn skip_ignorable(sql: &str, mut index: usize) -> Result<usize, String> {
    loop {
        index = skip_whitespace(sql, index);
        if sql[index..].starts_with("--") {
            index = sql[index..]
                .find('\n')
                .map_or(sql.len(), |value| index + value + 1);
        } else if sql[index..].starts_with("/*") {
            index = sql[index + 2..].find("*/").map_or_else(
                || Err("SQL test contains an unclosed block comment".to_owned()),
                |value| Ok(index + 2 + value + 2),
            )?;
        } else {
            return Ok(index);
        }
    }
}

fn skip_non_code(sql: &str, index: usize) -> Result<usize, String> {
    if sql[index..].starts_with("--") {
        return Ok(sql[index..]
            .find('\n')
            .map_or(sql.len(), |value| index + value + 1));
    }
    if sql[index..].starts_with("/*") {
        return sql[index + 2..]
            .find("*/")
            .map(|value| index + 2 + value + 2)
            .ok_or_else(|| "SQL test contains an unclosed block comment".to_owned());
    }
    if matches!(byte_at(sql, index), Some(b'\'') | Some(b'"') | Some(b'`')) {
        return skip_quote(sql, index, "SQL test");
    }
    Ok(index)
}

fn skip_quote(sql: &str, start: usize, context: &str) -> Result<usize, String> {
    let quote = byte_at(sql, start).expect("quote");
    let mut index = start + 1;
    while index < sql.len() {
        if byte_at(sql, index) == Some(quote) {
            if byte_at(sql, index + 1) == Some(quote) {
                index += 2;
            } else {
                return Ok(index + 1);
            }
        } else {
            index += char_len(sql, index)
        }
    }
    Err(format!("{context} contains an unclosed quoted string"))
}

fn matching_paren(sql: &str, open: usize, context: &str) -> Result<usize, String> {
    let mut depth = 0;
    let mut index = open;
    while index < sql.len() {
        let next = skip_non_code(sql, index)?;
        if next != index {
            index = next;
            continue;
        }
        match byte_at(sql, index) {
            Some(b'(') => depth += 1,
            Some(b')') => {
                depth -= 1;
                if depth == 0 {
                    return Ok(index);
                }
            }
            _ => {}
        }
        index += char_len(sql, index);
    }
    Err(format!("{context} contains an unclosed parenthesis"))
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
            let c = sql[index..].chars().next().expect("character");
            value.push(c);
            index += c.len_utf8();
        }
    }
    Err("SQL test macro mock has an unterminated string literal".to_owned())
}
