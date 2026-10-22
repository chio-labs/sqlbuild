//! Probe queries that read the caller's column types at each SQL macro call, and their verdicts.

use serde_json::{Value, json};

use crate::query_analysis::main::analyze::analyze_json;
use crate::sql_macros::_helpers::arguments::{fits, type_family};
use crate::sql_macros::_helpers::header::unquoted;
use crate::sql_macros::_helpers::lexing::{Token, TokenKind, tokens};
use crate::sql_macros::_helpers::placement::{QueryParts, top_level_parts};
use crate::sql_macros::constants::{
    FROM_KEYWORD, INFERRED_TEXT_TYPE, PROBE_COLUMN_PREFIX, PROBE_TAIL_ENDS, STAR_PROJECTION,
    UNKNOWN_TYPE_HINT, VARCHAR_TYPE,
};
use crate::sql_macros::models::{
    ArgumentCheck, ArgumentExpectation, CallScope, SqlMacroCheck, SqlMacroFinding,
};
use crate::sql_macros::types::{ProbeColumns, RelationShapes};

/// Where one argument's evidence is: a probe's whole column list, or one probe column.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum Evidence {
    Columns(usize),
    Column(usize, String),
}

/// The probes of one model and, per check and argument, where its evidence is.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct ProbePlan {
    pub(crate) probes: Vec<String>,
    pub(crate) evidence: Vec<Vec<Option<Evidence>>>,
}

/// The CTE definitions before index `end` as a `WITH` prefix, empty when there are none.
fn with_prefix(sql: &str, parts: &QueryParts, end: usize) -> String {
    let definitions: Vec<&str> = parts.ctes[..end]
        .iter()
        .map(|cte| &sql[cte.definition.0..cte.definition.1])
        .collect();
    if definitions.is_empty() {
        String::new()
    } else {
        format!("WITH {} ", definitions.join(", "))
    }
}

/// The `FROM ... WHERE ...` text of the first select of `body`, with no later clauses.
fn from_tail(body: &str) -> Option<String> {
    let Ok(scanned) = tokens(body) else {
        return None;
    };
    let first: &Token = scanned.first()?;
    if !first.is_word(body, "SELECT") {
        return None;
    }
    let mut depth: usize = 0;
    let mut from: Option<usize> = None;
    for token in &scanned {
        if token.kind == TokenKind::Punct {
            match token.text(body) {
                "(" | "[" | "{" => depth += 1,
                ")" | "]" | "}" => depth = depth.saturating_sub(1),
                ";" if depth == 0 => return from.map(|start| body[start..token.start].to_owned()),
                _ => {}
            }
            continue;
        }
        if depth != 0 || token.kind != TokenKind::Word {
            continue;
        }
        let upper: String = token.text(body).to_ascii_uppercase();
        match from {
            None if upper == FROM_KEYWORD => from = Some(token.start),
            Some(start) if PROBE_TAIL_ENDS.contains(&upper.as_str()) => {
                return Some(body[start..token.start].to_owned());
            }
            _ => {}
        }
    }
    Some(from.map_or_else(String::new, |start| body[start..].to_owned()))
}

/// The `WITH` prefix and `FROM` tail a probe at `scope` selects through.
fn scope_frame(sql: &str, parts: &QueryParts, scope: &CallScope) -> Option<(String, String)> {
    match scope {
        CallScope::WithList => None,
        CallScope::Main => Some((
            with_prefix(sql, parts, parts.ctes.len()),
            from_tail(&sql[parts.main..])?,
        )),
        CallScope::Cte(name) => {
            let index: usize = parts
                .ctes
                .iter()
                .position(|cte| cte.name.eq_ignore_ascii_case(name))?;
            let body: (usize, usize) = parts.ctes[index].body;
            Some((
                with_prefix(sql, parts, index),
                from_tail(sql[body.0..body.1].trim())?,
            ))
        }
    }
}

/// The probe listing the columns of relation `name` as the call at `scope` sees it.
fn relation_probe(sql: &str, parts: &QueryParts, scope: &CallScope, name: &str) -> Option<String> {
    let bare: String = unquoted(name);
    if let Some(index) = parts
        .ctes
        .iter()
        .position(|cte| cte.name.eq_ignore_ascii_case(&bare))
    {
        return Some(format!(
            "{}SELECT * FROM {name}",
            with_prefix(sql, parts, index + 1)
        ));
    }
    let (prefix, tail) = scope_frame(sql, parts, scope)?;
    (!tail.is_empty()).then(|| format!("{prefix}SELECT {name}.* {tail}"))
}

/// The probes reading every check's evidence from the analysed query `sql`.
pub(crate) fn probe_plan(sql: &str, checks: &[SqlMacroCheck]) -> ProbePlan {
    let mut plan: ProbePlan = ProbePlan::default();
    let parts: Option<QueryParts> = match tokens(sql) {
        Ok(scanned) => top_level_parts(sql, &scanned),
        Err(_) => None,
    };
    let Some(parts) = parts else {
        plan.evidence = checks
            .iter()
            .map(|check| vec![None; check.arguments.len()])
            .collect();
        return plan;
    };
    for check in checks {
        let mut evidence: Vec<Option<Evidence>> = vec![None; check.arguments.len()];
        let mut typed: Vec<String> = Vec::new();
        let mut typed_arguments: Vec<usize> = Vec::new();
        for (index, argument) in check.arguments.iter().enumerate() {
            match &argument.expected {
                ArgumentExpectation::Relation { .. } => {
                    if let Some(probe) = relation_probe(sql, &parts, &check.scope, &argument.text) {
                        plan.probes.push(probe);
                        evidence[index] = Some(Evidence::Columns(plan.probes.len() - 1));
                    }
                }
                ArgumentExpectation::Typed { .. } => {
                    typed.push(format!(
                        "({}) AS {PROBE_COLUMN_PREFIX}{}",
                        argument.text,
                        typed.len()
                    ));
                    typed_arguments.push(index);
                }
                ArgumentExpectation::ColumnOf { .. } => {}
            }
        }
        if !typed.is_empty()
            && let Some((prefix, tail)) = scope_frame(sql, &parts, &check.scope)
        {
            plan.probes
                .push(format!("{prefix}SELECT {} {tail}", typed.join(", ")));
            let probe: usize = plan.probes.len() - 1;
            for (position, index) in typed_arguments.into_iter().enumerate() {
                evidence[index] = Some(Evidence::Column(
                    probe,
                    format!("{PROBE_COLUMN_PREFIX}{position}"),
                ));
            }
        }
        plan.evidence.push(evidence);
    }
    plan
}

/// The column type of `name` in `columns`, matching names without case or quotes.
fn column_type<'c>(
    columns: &'c [(String, Option<String>)],
    name: &str,
) -> Option<&'c Option<String>> {
    let bare: String = unquoted(name);
    columns
        .iter()
        .find(|(column, _)| unquoted(column).eq_ignore_ascii_case(&bare))
        .map(|(_, data_type)| data_type)
}

/// Whether a value of type `actual` fits where `expected` is declared, unknown types fitting.
fn compatible(actual: Option<&str>, expected: &str, dialect: &str) -> bool {
    let Some(actual) = actual else {
        return true;
    };
    fits(type_family(actual, dialect), type_family(expected, dialect))
}

/// The findings of one check, given each probe's columns where its analysis knew them.
pub(crate) fn check_findings(
    (check, evidence): (&SqlMacroCheck, &[Option<Evidence>]),
    results: &[ProbeColumns],
    dialect: &str,
) -> Vec<SqlMacroFinding> {
    let Some((call, call_end)) = &check.call else {
        return Vec::new();
    };
    let finding =
        |argument: &ArgumentCheck, message: String, help: Option<String>| SqlMacroFinding {
            message,
            help,
            call: call.clone(),
            call_end: *call_end,
            declared_at: argument.declared_at.clone(),
        };
    let columns_of = |index: usize| -> Option<&Vec<(String, Option<String>)>> {
        match evidence.get(index)?.as_ref()? {
            Evidence::Columns(probe) => results.get(*probe)?.as_ref(),
            Evidence::Column(..) => None,
        }
    };
    let name: &str = &check.macro_name;
    let mut findings: Vec<SqlMacroFinding> = Vec::new();
    for (index, argument) in check.arguments.iter().enumerate() {
        let parameter: &str = &argument.parameter;
        match &argument.expected {
            ArgumentExpectation::Relation { columns } => {
                let Some(found) = columns_of(index) else {
                    continue;
                };
                let listed: Vec<String> = columns
                    .iter()
                    .map(|(column, data_type)| format!("{column} {data_type}"))
                    .collect();
                for (column, data_type) in columns {
                    let reason: Option<String> = match column_type(found, column) {
                        None => Some(format!("{} has no column {column}", argument.text)),
                        Some(actual) if !compatible(actual.as_deref(), data_type, dialect) => {
                            Some(format!(
                                "{}.{column} is {}",
                                argument.text,
                                shown_type(actual.as_deref().unwrap_or_default())
                            ))
                        }
                        Some(_) => None,
                    };
                    if let Some(reason) = reason {
                        findings.push(finding(
                            argument,
                            format!("argument {parameter} of macro {name}() needs column {column} {data_type}; {reason}"),
                            Some(format!("pass a relation with these columns: {}", listed.join(", "))),
                        ));
                        break;
                    }
                }
            }
            ArgumentExpectation::ColumnOf { relation } => {
                let Some(source) = check
                    .arguments
                    .iter()
                    .position(|other| other.parameter == *relation)
                else {
                    continue;
                };
                let Some(found) = columns_of(source) else {
                    continue;
                };
                if column_type(found, &argument.text).is_none() {
                    findings.push(finding(
                        argument,
                        format!(
                            "argument {parameter} of macro {name}() expects COLUMN OF {relation}; {} has no column {}",
                            check.arguments[source].text, argument.text
                        ),
                        Some(format!(
                            "pass one of the columns of {}",
                            check.arguments[source].text
                        )),
                    ));
                }
            }
            ArgumentExpectation::Typed { data_type } => {
                let Some(Some(Evidence::Column(probe, column))) = evidence.get(index) else {
                    continue;
                };
                let Some(Some(found)) = results.get(*probe) else {
                    continue;
                };
                let Some(Some(actual)) = column_type(found, column) else {
                    continue;
                };
                if !compatible(Some(actual), data_type, dialect) {
                    findings.push(finding(
                        argument,
                        format!(
                            "argument {parameter} of macro {name}() expects {data_type}; {} is {}",
                            argument.text,
                            shown_type(actual)
                        ),
                        None,
                    ));
                }
            }
        }
    }
    findings
}

/// An inferred type as messages show it, in the SQL type names schema declarations use.
fn shown_type(inferred: &str) -> &str {
    if inferred.eq_ignore_ascii_case(INFERRED_TEXT_TYPE) {
        VARCHAR_TYPE
    } else {
        inferred
    }
}

/// Each probe's output columns, analysed against `schema`; `None` where analysis knew none.
pub(crate) fn analysed_probes(
    dialect: &str,
    probes: &[String],
    schema: &RelationShapes,
) -> Option<Vec<ProbeColumns>> {
    let tables: Vec<Value> = schema
        .iter()
        .map(|(name, columns)| table(name, columns))
        .collect();
    let requests: Vec<Value> = probes
        .iter()
        .map(|sql| json!({"sql": sql, "dialect": dialect, "schema": {"tables": tables}}))
        .collect();
    let Ok(response) = analyze_json(&json!({ "requests": requests }).to_string()) else {
        return None;
    };
    let Ok(Value::Array(analyses)) = serde_json::from_str::<Value>(&response) else {
        return None;
    };
    Some(analyses.iter().map(probe_columns).collect())
}

/// One bound relation as a validation schema table, its qualified name split into parts.
fn table(name: &str, columns: &[(String, String)]) -> Value {
    let mut parts: Vec<&str> = name.split('.').collect();
    let table_name: &str = parts.pop().unwrap_or(name);
    let columns: Vec<Value> = columns
        .iter()
        .map(|(column, data_type)| json!({"name": column, "type": data_type}))
        .collect();
    let mut entry: Value = json!({"name": table_name, "columns": columns});
    if let Some(schema) = parts.pop() {
        entry["schema"] = json!(schema);
    }
    if let Some(catalog) = parts.pop() {
        entry["catalog"] = json!(catalog);
    }
    entry
}

/// A probe analysis's output columns, unless it failed or left a star unresolved.
fn probe_columns(analysis: &Value) -> ProbeColumns {
    let projections: &Vec<Value> = analysis.pointer("/analysis/projections")?.as_array()?;
    let mut columns: Vec<(String, Option<String>)> = Vec::with_capacity(projections.len());
    for projection in projections {
        let name: &str = projection.get("name")?.as_str()?;
        let star: bool = projection.get("isStar").and_then(Value::as_bool) == Some(true);
        if star || name == STAR_PROJECTION {
            return None;
        }
        let hint: Option<&str> = projection.get("typeHint").and_then(Value::as_str);
        let data_type: Option<String> = match hint {
            Some(hint) if !hint.eq_ignore_ascii_case(UNKNOWN_TYPE_HINT) => Some(hint.to_owned()),
            _ => None,
        };
        columns.push((name.to_owned(), data_type));
    }
    Some(columns)
}
