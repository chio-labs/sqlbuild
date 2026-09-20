//! Deterministic comparison SQL rendering for planned SQL-native tests.

use std::collections::HashMap;

use polyglot_sql::{Dialect, DialectType, Expression};
use rayon::iter::{IntoParallelIterator, ParallelIterator};
use serde::{Deserialize, Serialize};

const DEFAULT_WORKERS: usize = 4;
const MAX_WORKERS: usize = 4;
const WORKER_STACK_BYTES: usize = 16 * 1024 * 1024;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RenderBatchRequest {
    requests: Vec<RenderRequest>,
    #[serde(default = "default_workers")]
    workers: usize,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct RenderRequest {
    #[serde(default)]
    pub(crate) chain: Vec<ChainStep>,
    #[serde(default)]
    pub(crate) assertions: Vec<AssertionStep>,
    #[serde(default = "default_true")]
    pub(crate) sql_analysis_enabled: bool,
    #[serde(default = "default_set_difference")]
    pub(crate) set_difference_operator: String,
    #[serde(default, rename = "sqlAnalysisDialect")]
    pub(crate) _sql_analysis_dialect: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ChainStep {
    pub(crate) model_name: String,
    pub(crate) resolved_sql: String,
    #[serde(default)]
    pub(crate) expected_cte_sql: Option<String>,
    #[serde(default)]
    pub(crate) lifted_ctes: Vec<(String, String)>,
    #[serde(default)]
    pub(crate) comparison_body_sql: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct AssertionStep {
    pub(crate) name: String,
    pub(crate) resolved_sql: String,
    #[serde(default)]
    pub(crate) lifted_ctes: Vec<(String, String)>,
    #[serde(default)]
    pub(crate) comparison_body_sql: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct RenderResponse {
    sql: String,
}

pub(crate) fn render_json(request_json: &str) -> Result<String, String> {
    let request: RenderBatchRequest =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    let workers = request.workers.clamp(1, MAX_WORKERS);
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(workers.min(request.requests.len().max(1)))
        .stack_size(WORKER_STACK_BYTES)
        .build()
        .map_err(|error| error.to_string())?;
    let responses: Vec<RenderResponse> = pool.install(|| {
        request
            .requests
            .into_par_iter()
            .map(|request| RenderResponse {
                sql: render_comparison_sql(request),
            })
            .collect()
    });
    serde_json::to_string(&responses).map_err(|error| error.to_string())
}

pub(crate) fn render_comparison_sql(request: RenderRequest) -> String {
    if request.chain.is_empty() && request.assertions.is_empty() {
        return String::new();
    }
    let mut lifted_ctes = Vec::new();
    let mut comparison_ctes = Vec::new();
    let mut select_parts = Vec::new();
    let mut cte_name_counts = HashMap::new();

    for (step_index, step) in request.chain.iter().enumerate() {
        let suffix = unique_cte_suffix(&step.model_name, &mut cte_name_counts);
        let actual_cte = format!("__actual__{suffix}");
        let expected_cte = format!("__expected__{suffix}");
        if step.expected_cte_sql.is_none()
            && !assertions_use_actual(&request.assertions, &actual_cte)
        {
            continue;
        }
        let actual_sql = if step.lifted_ctes.is_empty() {
            lift_step_ctes(
                &step.resolved_sql,
                &mut lifted_ctes,
                request.sql_analysis_enabled,
            )
        } else {
            merge_lifted_ctes(&step.lifted_ctes, &mut lifted_ctes);
            lift_step_ctes(
                step.comparison_body_sql
                    .as_deref()
                    .unwrap_or(&step.resolved_sql),
                &mut lifted_ctes,
                request.sql_analysis_enabled,
            )
        };
        comparison_ctes.push(cte_definition_sql(&actual_cte, &actual_sql));
        let Some(expected_input) = step.expected_cte_sql.as_deref() else {
            continue;
        };
        let expected_sql = lift_step_ctes(
            expected_input,
            &mut lifted_ctes,
            request.sql_analysis_enabled,
        );
        comparison_ctes.push(cte_definition_sql(&expected_cte, &expected_sql));
        select_parts.push(format!(
            "SELECT {step_index} AS step_index, '{}' AS model_name, \
             (SELECT COUNT(*) FROM {actual_cte}) AS actual_count, \
             (SELECT COUNT(*) FROM {expected_cte}) AS expected_count, \
             (SELECT COUNT(*) FROM (SELECT * FROM {actual_cte} {} SELECT * FROM {expected_cte}) AS __sqlbuild_mismatch) AS unexpected_count, \
             (SELECT COUNT(*) FROM (SELECT * FROM {expected_cte} {} SELECT * FROM {actual_cte}) AS __sqlbuild_missing) AS missing_count",
            escape_sql_string(&step.model_name),
            request.set_difference_operator,
            request.set_difference_operator,
        ));
    }

    for (assertion_index, assertion) in request
        .assertions
        .iter()
        .enumerate()
        .map(|(index, assertion)| (index + request.chain.len(), assertion))
    {
        let suffix = unique_cte_suffix(&assertion.name, &mut cte_name_counts);
        let assertion_cte = format!("__assert__{suffix}");
        let assertion_input = assertion
            .comparison_body_sql
            .as_deref()
            .unwrap_or(&assertion.resolved_sql);
        if !assertion.lifted_ctes.is_empty() {
            merge_lifted_ctes(&assertion.lifted_ctes, &mut lifted_ctes);
        }
        let assertion_sql = lift_step_ctes(
            assertion_input,
            &mut lifted_ctes,
            request.sql_analysis_enabled,
        );
        comparison_ctes.push(cte_definition_sql(&assertion_cte, &assertion_sql));
        select_parts.push(format!(
            "SELECT {assertion_index} AS step_index, 'assertion {}' AS model_name, \
             (SELECT COUNT(*) FROM {assertion_cte}) AS actual_count, \
             0 AS expected_count, \
             (SELECT COUNT(*) FROM {assertion_cte}) AS unexpected_count, \
             0 AS missing_count",
            escape_sql_string(&assertion.name),
        ));
    }

    if select_parts.is_empty() {
        return String::new();
    }
    let mut cte_parts: Vec<String> = lifted_ctes
        .iter()
        .map(|(name, sql)| cte_definition_sql(name, sql))
        .collect();
    cte_parts.extend(comparison_ctes);
    format!(
        "WITH {}\n{}",
        cte_parts.join(",\n"),
        select_parts.join("\nUNION ALL\n")
    )
}

fn lift_step_ctes(sql: &str, lifted: &mut Vec<(String, String)>, enabled: bool) -> String {
    if !enabled {
        return sql.to_string();
    }
    let Some((step_ctes, body_sql)) = split_top_level_with(sql) else {
        return sql.to_string();
    };
    if step_ctes.iter().any(|(name, body)| {
        existing_cte(lifted, name).is_some_and(|(_, existing)| existing != body)
    }) {
        return sql.to_string();
    }
    merge_lifted_ctes(&step_ctes, lifted);
    body_sql
}

fn merge_lifted_ctes(ctes: &[(String, String)], lifted: &mut Vec<(String, String)>) {
    for (name, sql) in ctes {
        if existing_cte(lifted, name).is_none() {
            lifted.push((name.clone(), sql.clone()));
        }
    }
}

fn existing_cte<'a>(lifted: &'a [(String, String)], name: &str) -> Option<&'a (String, String)> {
    lifted
        .iter()
        .find(|(existing, _)| existing.eq_ignore_ascii_case(name))
}

fn split_top_level_with(sql: &str) -> Option<(Vec<(String, String)>, String)> {
    let (protected, identifiers) = protect_backtick_identifiers(sql);
    let dialect = Dialect::get(DialectType::Generic);
    let mut statements = dialect.parse(&protected).ok()?;
    if statements.len() != 1 {
        return None;
    }
    let mut expression = statements.pop()?;
    let Expression::Select(select) = &mut expression else {
        return None;
    };
    let with = select.with.take()?;
    let mut ctes = Vec::with_capacity(with.ctes.len());
    for cte in with.ctes {
        let sql = dialect.generate(&cte.this).ok()?;
        ctes.push((
            cte.alias.name,
            restore_backtick_identifiers(&sql, &identifiers),
        ));
    }
    let body = dialect.generate(&expression).ok()?;
    Some((ctes, restore_backtick_identifiers(&body, &identifiers)))
}

fn protect_backtick_identifiers(sql: &str) -> (String, Vec<(String, String)>) {
    let mut protected = String::with_capacity(sql.len());
    let mut identifiers = Vec::new();
    let mut cursor = 0;
    while let Some(relative_start) = sql[cursor..].find('`') {
        let start = cursor + relative_start;
        protected.push_str(&sql[cursor..start]);
        cursor = start + 1;
        let start = cursor;
        loop {
            let Some(relative_end) = sql[cursor..].find('`') else {
                protected.push_str(&sql[start - 1..]);
                return (protected, identifiers);
            };
            cursor += relative_end + 1;
            let remainder = &sql[cursor..];
            let whitespace_len = remainder.len() - remainder.trim_start().len();
            let dot_index = cursor + whitespace_len;
            if !sql[dot_index..].starts_with('.') {
                break;
            }
            let after_dot = dot_index + 1;
            let dot_remainder = &sql[after_dot..];
            let dot_whitespace_len = dot_remainder.len() - dot_remainder.trim_start().len();
            let next_identifier = after_dot + dot_whitespace_len;
            if !sql[next_identifier..].starts_with('`') {
                break;
            }
            cursor = next_identifier + 1;
        }
        let placeholder = format!("SQB_PROTECTED_IDENTIFIER_{}", identifiers.len());
        identifiers.push((placeholder.clone(), sql[start - 1..cursor].to_string()));
        protected.push_str(&placeholder);
    }
    protected.push_str(&sql[cursor..]);
    (protected, identifiers)
}

fn restore_backtick_identifiers(sql: &str, identifiers: &[(String, String)]) -> String {
    identifiers
        .iter()
        .fold(sql.to_string(), |value, (placeholder, identifier)| {
            value.replace(placeholder, identifier)
        })
}

fn unique_cte_suffix(model_name: &str, counts: &mut HashMap<String, usize>) -> String {
    let base = sanitize_cte_suffix(model_name);
    let count = counts.entry(base.clone()).or_default();
    *count += 1;
    if *count == 1 {
        base
    } else {
        format!("{base}_{count}")
    }
}

fn sanitize_cte_suffix(model_name: &str) -> String {
    let mut suffix = String::with_capacity(model_name.len());
    let mut previous_separator = false;
    for character in model_name.chars() {
        if character.is_ascii_alphanumeric() || character == '_' {
            suffix.push(character.to_ascii_lowercase());
            previous_separator = false;
        } else if !previous_separator {
            suffix.push('_');
            previous_separator = true;
        }
    }
    let suffix = suffix.trim_matches('_');
    if suffix.is_empty() {
        "model".to_string()
    } else if suffix.as_bytes()[0].is_ascii_digit() {
        format!("model_{suffix}")
    } else {
        suffix.to_string()
    }
}

fn cte_definition_sql(name: &str, sql: &str) -> String {
    let body = sql.trim_end();
    let final_line = body.rsplit_once('\n').map_or(body, |(_, line)| line);
    let terminator = if final_line.contains("--") { "\n" } else { "" };
    format!("{name} AS ({body}{terminator})")
}

fn assertions_use_actual(assertions: &[AssertionStep], actual_cte: &str) -> bool {
    let needle = actual_cte.to_ascii_lowercase();
    assertions.iter().any(|assertion| {
        assertion
            .resolved_sql
            .to_ascii_lowercase()
            .contains(&needle)
    })
}

fn escape_sql_string(value: &str) -> String {
    value.replace('\'', "''")
}

fn default_workers() -> usize {
    DEFAULT_WORKERS
}

fn default_true() -> bool {
    true
}

fn default_set_difference() -> String {
    "EXCEPT".to_string()
}
