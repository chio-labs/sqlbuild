use crate::constants::{
    BOOLEAN_TYPE, DATE_TYPE, DECLARATION_DOMAIN_COMPONENTS, ENFORCED_CONTRACT, NEGATION_OPERATOR,
    REFERENCE_KIND, TIMESTAMP_TYPE, VIEW_MATERIALIZATION,
};
use crate::models::{Declaration, EvaluateRequest, Fault, Model, PolicyConfig, RuleMetadata};
use crate::rules::models::{FaultCollector, ModelEvaluationRequest, ResolvedThresholdOverride};
use globset::{Glob, GlobSetBuilder};
use sqlparser::ast::{
    BinaryOperator, Expr, GroupByExpr, JoinConstraint, JoinOperator, Query, Select, SelectItem,
    SetExpr, Spanned, Statement, TableFactor, Value, Visit, Visitor,
};
use sqlparser::dialect::{
    BigQueryDialect, ClickHouseDialect, DatabricksDialect, Dialect, DuckDbDialect, GenericDialect,
    MsSqlDialect, PostgreSqlDialect, SnowflakeDialect,
};
use sqlparser::parser::{Parser, ParserError, ParserOptions};
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::ops::ControlFlow;

const MIXED_STAR_REMEDIATION: &str = "SELECT *, a, b mixes a passthrough star with derived columns. The * exemption permits a lone SELECT * only. Move a and b into an earlier CTE so they are computed upstream, leaving the final select a pure SELECT *. If you need those columns in the output, drop the * exemption and enumerate every column explicitly.";
const POLICY_PARSER_RECURSION_LIMIT: usize = 128;

#[derive(Clone)]
struct Position {
    line: u64,
    column: u64,
}

#[derive(Default)]
struct ComparisonFact {
    position: Option<Position>,
    columns: BTreeSet<String>,
    string_literals: Vec<String>,
    numeric_literals: Vec<String>,
    modified_columns: BTreeSet<ColumnFact>,
    modified_string_literal: bool,
    source_context: SourceContext,
}

#[derive(Clone, Eq, Ord, PartialEq, PartialOrd)]
struct ColumnFact {
    name: String,
    qualifier: Option<String>,
}

#[derive(Clone, Default)]
struct SourceContext {
    relations: BTreeSet<String>,
    sole_relation: bool,
}

#[derive(Default)]
struct SelectFacts {
    comparisons: Vec<ComparisonFact>,
}

struct ParsedModel<'a> {
    query: Query,
    model: &'a Model,
    classification: ModelClassification,
}

struct ModelClassification {
    authored_dependencies: Vec<String>,
    ctes: Vec<CteClassification>,
    passthrough: bool,
}

struct TestRuleEvaluation<'a> {
    parsed: &'a ParsedModel<'a>,
    config: &'a PolicyConfig,
    threshold_overrides: &'a [ResolvedThresholdOverride],
    selected: &'a BTreeMap<String, &'a RuleMetadata>,
    faults: &'a FaultCollector,
}

struct CteClassification {
    name: String,
    position: Position,
    dependency_import: bool,
    kind: CteKind,
}

enum CteKind {
    Logical,
    Import {
        dependencies: Vec<String>,
        rejections: Vec<ImportRejection>,
    },
}

enum ImportRejection {
    MultipleDependencies,
    AfterLogical,
    Transformation,
}

pub(crate) fn evaluate_model(request: ModelEvaluationRequest<'_>) -> Result<Vec<Fault>, String> {
    stacker::grow(8 * 1024 * 1024, || evaluate_model_inner(request))
}

fn evaluate_model_inner(request: ModelEvaluationRequest<'_>) -> Result<Vec<Fault>, String> {
    let ModelEvaluationRequest {
        model,
        config,
        selected,
        request,
        is_anchor,
        threshold_overrides,
    } = request;
    let parser_sql = normalize_policy_sql(&request.dialect, &model.query_sql);
    let mut statements =
        parse_policy_statements(&parser_sql, &request.dialect).map_err(|error| {
            format!(
                "could not parse {} for policy: {error}",
                model.relative_path
            )
        })?;
    if statements.len() != 1 {
        return Err(format!(
            "could not parse {} for policy: expected one statement",
            model.relative_path
        ));
    }
    let statement = statements.remove(0);
    let sqlparser::ast::Statement::Query(query) = statement else {
        return Err(format!(
            "could not parse {} for policy: expected a query",
            model.relative_path
        ));
    };
    let query = *query;
    let classification = classify_model(&query, model);
    let parsed = ParsedModel {
        query,
        model,
        classification,
    };
    let metadata = |code: &str| selected.get(code).copied();
    let faults = FaultCollector::default();

    if let Some(rule) = metadata("SQBPS101") {
        import_ctes(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBPS102") {
        select_star(&parsed, config, rule, &faults)?;
    }
    if let Some(rule) = metadata("SQBPS103") {
        view_marker(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBPG101") {
        forward_refs(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBPG102") {
        raw_qualified_tables(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBPR101") {
        name_grammar(&parsed, config, rule, &faults);
    }
    if let Some(rule) = metadata("SQBPR102") {
        folder_layer(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBPR103") {
        source_token_policy(&parsed, config, rule, &faults);
    }
    if let Some(rule) = metadata("SQBPR104") {
        reference_name_policy(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBPC101") {
        contract_required(&parsed, rule, &faults);
    }
    evaluate_naming_rules(&parsed, selected, &faults);
    evaluate_literal_rules(&parsed, selected, &faults);
    evaluate_test_rules(TestRuleEvaluation {
        parsed: &parsed,
        config,
        threshold_overrides,
        selected,
        faults: &faults,
    });

    if is_anchor {
        if let Some(rule) = metadata("SQBPD201") {
            duplicate_enums(request, rule, &faults);
        }
        if let Some(rule) = metadata("SQBPD301") {
            declaration_domain_placement(request, config, rule, &faults);
        }
        if let Some(rule) = metadata("SQBPT301") {
            custom_rule_test_coverage(request, config, (selected, rule), &faults);
        }
    }
    Ok(faults.into_inner())
}

fn parse_policy_statements(sql: &str, dialect_name: &str) -> Result<Vec<Statement>, ParserError> {
    let dialect = policy_dialect(dialect_name);
    match parse_with_dialect(sql, dialect.as_ref()) {
        Ok(statements) => Ok(statements),
        Err(primary) if !dialect_name.eq_ignore_ascii_case("generic") => {
            let fallback_sql = normalize_generic_fallback(sql);
            parse_with_dialect(&fallback_sql, &GenericDialect {}).map_err(|fallback| {
                ParserError::ParserError(format!(
                    "{primary}; generic fallback also failed: {fallback}"
                ))
            })
        }
        Err(error) => Err(error),
    }
}

fn normalize_generic_fallback(sql: &str) -> String {
    let mut bytes = sql.as_bytes().to_vec();
    let mut quote: Option<u8> = None;
    let mut index = 0;
    while index < bytes.len() {
        let byte = bytes[index];
        let next = bytes.get(index + 1).copied();
        if let Some(active_quote) = quote {
            if byte == active_quote {
                if next == Some(active_quote) {
                    index += 2;
                    continue;
                }
                quote = None;
            }
            index += 1;
            continue;
        }
        if matches!(byte, b'\'' | b'"') {
            quote = Some(byte);
        } else if byte == b'-' && next == Some(b'>') {
            bytes[index] = b',';
            bytes[index + 1] = b' ';
            index += 2;
            continue;
        } else if byte == b':'
            && bytes.get(index.wrapping_sub(1)) != Some(&b':')
            && next != Some(b':')
        {
            bytes[index] = b'.';
        }
        index += 1;
    }
    String::from_utf8(bytes).unwrap_or_else(|_| sql.to_owned())
}

fn parse_with_dialect(sql: &str, dialect: &dyn Dialect) -> Result<Vec<Statement>, ParserError> {
    let mut parser = Parser::new(dialect)
        .with_options(ParserOptions::new().with_trailing_commas(true))
        .with_recursion_limit(POLICY_PARSER_RECURSION_LIMIT)
        .try_with_sql(sql)?;
    parser.parse_statements()
}

fn policy_dialect(name: &str) -> Box<dyn Dialect> {
    match name.to_ascii_lowercase().as_str() {
        "bigquery" => Box::new(BigQueryDialect {}),
        "clickhouse" => Box::new(ClickHouseDialect {}),
        "databricks" => Box::new(DatabricksDialect {}),
        "duckdb" => Box::new(DuckDbDialect {}),
        "postgres" | "postgresql" => Box::new(PostgreSqlDialect {}),
        "mssql" | "sqlserver" | "tsql" => Box::new(MsSqlDialect {}),
        "snowflake" => Box::new(SnowflakeDialect {}),
        _ => Box::new(GenericDialect {}),
    }
}

pub(crate) fn normalize_policy_sql(dialect: &str, sql: &str) -> String {
    let sql = normalize_table_function_calls(sql);
    if !dialect.eq_ignore_ascii_case("snowflake") {
        return sql;
    }
    let mut bytes = sql.as_bytes().to_vec();
    let mut index = 0;
    let mut quote: Option<u8> = None;
    let mut line_comment = false;
    let mut block_comment = false;
    while index < bytes.len() {
        let byte = bytes[index];
        let next = bytes.get(index + 1).copied();
        if line_comment {
            line_comment = byte != b'\n';
            index += 1;
            continue;
        }
        if block_comment {
            if byte == b'*' && next == Some(b'/') {
                block_comment = false;
                index += 2;
            } else {
                index += 1;
            }
            continue;
        }
        if let Some(active_quote) = quote {
            if byte == active_quote {
                if next == Some(active_quote) {
                    index += 2;
                    continue;
                }
                quote = None;
            }
            index += 1;
            continue;
        }
        if byte == b'-' && next == Some(b'-') {
            line_comment = true;
            index += 2;
            continue;
        }
        if byte == b'/' && next == Some(b'*') {
            block_comment = true;
            index += 2;
            continue;
        }
        if matches!(byte, b'\'' | b'"') {
            quote = Some(byte);
            index += 1;
            continue;
        }
        if byte == b',' && clause_follows(&bytes, index + 1) {
            bytes[index] = b' ';
            index += 1;
            continue;
        }
        if byte.is_ascii_alphabetic() {
            let start = index;
            while index < bytes.len()
                && (bytes[index].is_ascii_alphanumeric() || bytes[index] == b'_')
            {
                index += 1;
            }
            let word = &sql.as_bytes()[start..index];
            let mut following = index;
            while bytes.get(following).is_some_and(u8::is_ascii_whitespace) {
                following += 1;
            }
            if word.eq_ignore_ascii_case(b"EXCLUDE")
                && is_star_modifier_before(sql.as_bytes(), start)
                && bytes.get(following) == Some(&b'(')
                && let Some(close) = matching_parenthesis(&bytes, following)
            {
                blank_preserving_newlines(&mut bytes[start..=close]);
                index = close + 1;
                continue;
            }
            if word.eq_ignore_ascii_case(b"ARRAY")
                && is_cast_type_before(sql.as_bytes(), start)
                && bytes.get(following) == Some(&b'(')
                && let Some(close) = matching_parenthesis(&bytes, following)
            {
                bytes[start..index].copy_from_slice(b"TEXT ");
                blank_preserving_newlines(&mut bytes[following..=close]);
                index = close + 1;
                continue;
            }
            let typed_lambda = bytes.get(following) == Some(&b'-')
                && bytes.get(following + 1) == Some(&b'>')
                && is_lambda_parameter_before(sql.as_bytes(), start)
                && is_lambda_parameter_type(word);
            if typed_lambda {
                bytes[start..index].fill(b' ');
            }
            continue;
        }
        index += 1;
    }
    String::from_utf8(bytes).unwrap_or(sql)
}

fn normalize_table_function_calls(sql: &str) -> String {
    const TABLE_FUNCTION: &[u8] = b"__table_fn(";
    let mut bytes = sql.as_bytes().to_vec();
    let mut cursor = 0;
    while cursor + TABLE_FUNCTION.len() <= bytes.len() {
        let Some(token_start) = find_token_outside_syntax(&bytes, TABLE_FUNCTION, cursor) else {
            break;
        };
        let open = token_start + TABLE_FUNCTION.len() - 1;
        let Some(close) = matching_parenthesis(&bytes, open) else {
            break;
        };
        let mut next = close + 1;
        while bytes.get(next).is_some_and(u8::is_ascii_whitespace) {
            next += 1;
        }
        if bytes.get(next) == Some(&b'(') {
            bytes[close] = b',';
            bytes[next] = b' ';
        }
        cursor = next.saturating_add(1);
    }
    String::from_utf8(bytes).unwrap_or_else(|_| sql.to_owned())
}

fn blank_preserving_newlines(sql: &mut [u8]) {
    for byte in sql {
        if !matches!(*byte, b'\n' | b'\r') {
            *byte = b' ';
        }
    }
}

fn find_token_outside_syntax(sql: &[u8], token: &[u8], start: usize) -> Option<usize> {
    let mut index = start;
    let mut quote: Option<u8> = None;
    let mut line_comment = false;
    let mut block_comment = false;
    while index + token.len() <= sql.len() {
        let byte = sql[index];
        let next = sql.get(index + 1).copied();
        if line_comment {
            line_comment = byte != b'\n';
            index += 1;
            continue;
        }
        if block_comment {
            if byte == b'*' && next == Some(b'/') {
                block_comment = false;
                index += 2;
            } else {
                index += 1;
            }
            continue;
        }
        if let Some(active_quote) = quote {
            if byte == active_quote {
                if next == Some(active_quote) {
                    index += 2;
                    continue;
                }
                quote = None;
            }
            index += 1;
            continue;
        }
        if byte == b'-' && next == Some(b'-') {
            line_comment = true;
            index += 2;
            continue;
        }
        if byte == b'/' && next == Some(b'*') {
            block_comment = true;
            index += 2;
            continue;
        }
        if matches!(byte, b'\'' | b'"') {
            quote = Some(byte);
            index += 1;
            continue;
        }
        if sql[index..index + token.len()].eq_ignore_ascii_case(token) {
            return Some(index);
        }
        index += 1;
    }
    None
}

fn clause_follows(sql: &[u8], start: usize) -> bool {
    let mut cursor = start;
    while sql.get(cursor).is_some_and(u8::is_ascii_whitespace) {
        cursor += 1;
    }
    [
        "FROM", "WHERE", "GROUP", "HAVING", "QUALIFY", "ORDER", "LIMIT",
    ]
    .iter()
    .any(|keyword| {
        let bytes = keyword.as_bytes();
        sql.get(cursor..cursor + bytes.len())
            .is_some_and(|candidate| candidate.eq_ignore_ascii_case(bytes))
            && sql
                .get(cursor + bytes.len())
                .is_none_or(|next| !next.is_ascii_alphanumeric() && *next != b'_')
    })
}

fn is_star_modifier_before(sql: &[u8], modifier_start: usize) -> bool {
    let mut cursor = modifier_start;
    while cursor > 0 && sql[cursor - 1].is_ascii_whitespace() {
        cursor -= 1;
    }
    cursor > 0 && sql[cursor - 1] == b'*'
}

fn is_cast_type_before(sql: &[u8], type_start: usize) -> bool {
    const AS_KEYWORD_LENGTH: usize = 2;
    const BYTE_BEFORE_AS_OFFSET: usize = 3;
    let mut cursor = type_start;
    while cursor > 0 && sql[cursor - 1].is_ascii_whitespace() {
        cursor -= 1;
    }
    cursor >= AS_KEYWORD_LENGTH
        && sql[cursor - AS_KEYWORD_LENGTH..cursor].eq_ignore_ascii_case(b"AS")
        && (cursor == AS_KEYWORD_LENGTH
            || !sql[cursor - BYTE_BEFORE_AS_OFFSET].is_ascii_alphanumeric())
}

fn matching_parenthesis(sql: &[u8], open: usize) -> Option<usize> {
    let mut depth = 0;
    let mut index = open;
    let mut quote: Option<u8> = None;
    let mut line_comment = false;
    let mut block_comment = false;
    while index < sql.len() {
        let byte = sql[index];
        let next = sql.get(index + 1).copied();
        if line_comment {
            line_comment = byte != b'\n';
            index += 1;
            continue;
        }
        if block_comment {
            if byte == b'*' && next == Some(b'/') {
                block_comment = false;
                index += 2;
            } else {
                index += 1;
            }
            continue;
        }
        if let Some(active_quote) = quote {
            if byte == active_quote {
                if next == Some(active_quote) {
                    index += 2;
                    continue;
                }
                quote = None;
            }
            index += 1;
            continue;
        }
        if byte == b'-' && next == Some(b'-') {
            line_comment = true;
            index += 2;
            continue;
        }
        if byte == b'/' && next == Some(b'*') {
            block_comment = true;
            index += 2;
            continue;
        }
        if matches!(byte, b'\'' | b'"') {
            quote = Some(byte);
            index += 1;
            continue;
        }
        match byte {
            b'(' => depth += 1,
            b')' => {
                depth -= 1;
                if depth == 0 {
                    return Some(index);
                }
            }
            _ => {}
        }
        index += 1;
    }
    None
}

fn is_lambda_parameter_before(sql: &[u8], type_start: usize) -> bool {
    let mut cursor = type_start;
    while cursor > 0 && sql[cursor - 1].is_ascii_whitespace() {
        cursor -= 1;
    }
    cursor > 0 && (sql[cursor - 1].is_ascii_alphanumeric() || sql[cursor - 1] == b'_')
}

fn is_lambda_parameter_type(word: &[u8]) -> bool {
    [
        b"INT".as_slice(),
        b"INTEGER".as_slice(),
        b"STRING".as_slice(),
        b"VARCHAR".as_slice(),
        b"BOOLEAN".as_slice(),
        b"FLOAT".as_slice(),
        b"DOUBLE".as_slice(),
    ]
    .iter()
    .any(|candidate| word.eq_ignore_ascii_case(candidate))
}

fn fault(model: &Model, rule: &RuleMetadata, position: Option<&Position>) -> Fault {
    Fault {
        code: rule.code.clone(),
        path: model.relative_path.clone(),
        line: position.map_or(1, |value| value.line),
        column: position.map_or(1, |value| value.column),
        message: rule.message.clone(),
        remediation: rule.remediation.clone(),
    }
}

fn custom_fault_impl(
    model: &Model,
    rule: &RuleMetadata,
    position: Option<&Position>,
    details: (String, Option<String>),
) -> Fault {
    let (message, remediation) = details;
    let mut result = fault(model, rule, position);
    result.message = message;
    if let Some(value) = remediation {
        result.remediation = value;
    }
    result
}

macro_rules! custom_fault {
    ($model:expr, $rule:expr, $position:expr, $message:expr, $remediation:expr $(,)?) => {
        custom_fault_impl($model, $rule, $position, ($message, $remediation))
    };
}

fn path_fault(path: &str, rule: &RuleMetadata, message: String, remediation: String) -> Fault {
    Fault {
        code: rule.code.clone(),
        path: path.into(),
        line: 1,
        column: 1,
        message,
        remediation,
    }
}

fn position<T: Spanned>(node: &T) -> Position {
    let start = node.span().start;
    Position {
        line: start.line,
        column: start.column,
    }
}

fn location_position(location: sqlparser::tokenizer::Location) -> Position {
    Position {
        line: location.line,
        column: location.column,
    }
}

fn root_select(query: &Query) -> Option<&Select> {
    query.body.as_select()
}

fn top_ctes(query: &Query) -> &[sqlparser::ast::Cte] {
    query
        .with
        .as_ref()
        .map_or(&[], |with| with.cte_tables.as_slice())
}

fn group_by_empty(group: &GroupByExpr) -> bool {
    matches!(group, GroupByExpr::Expressions(values, _) if values.is_empty())
}

fn direct_projection(item: &SelectItem, allow_star: bool) -> bool {
    match item {
        SelectItem::UnnamedExpr(Expr::Identifier(_) | Expr::CompoundIdentifier(_)) => true,
        SelectItem::ExprWithAlias { expr, .. } => {
            matches!(expr, Expr::Identifier(_) | Expr::CompoundIdentifier(_))
        }
        SelectItem::Wildcard(_) | SelectItem::QualifiedWildcard(_, _) => allow_star,
        _ => false,
    }
}

fn plain_projection(query: &Query, allow_star: bool) -> bool {
    if query.with.is_some() || query.order_by.is_some() || query.limit_clause.is_some() {
        return false;
    }
    let Some(select) = root_select(query) else {
        return false;
    };
    plain_select(select, allow_star)
}

fn plain_select(select: &Select, allow_star: bool) -> bool {
    if select.projection.is_empty()
        || select.selection.is_some()
        || select.having.is_some()
        || select.qualify.is_some()
        || !group_by_empty(&select.group_by)
        || select.from.iter().any(|source| !source.joins.is_empty())
    {
        return false;
    }
    if select.projection.len() == 1
        && matches!(
            select.projection[0],
            SelectItem::Wildcard(_) | SelectItem::QualifiedWildcard(_, _)
        )
    {
        return allow_star;
    }
    select
        .projection
        .iter()
        .all(|item| direct_projection(item, false))
}

fn dependency_name(factor: &TableFactor) -> Option<String> {
    let TableFactor::Table {
        name,
        args: Some(_),
        ..
    } = factor
    else {
        return None;
    };
    let value = name.to_string().to_ascii_lowercase();
    matches!(value.as_str(), "__ref" | "__source").then_some(value)
}

fn dependency_import(query: &Query) -> bool {
    let Some(select) = root_select(query) else {
        return false;
    };
    select.from.len() == 1
        && select.from[0].joins.is_empty()
        && dependency_name(&select.from[0].relation).is_some()
        && plain_projection(query, true)
}

fn sole_table_name(query: &Query) -> Option<String> {
    let select = root_select(query)?;
    if select.from.len() != 1 || !select.from[0].joins.is_empty() {
        return None;
    }
    let TableFactor::Table {
        name, args: None, ..
    } = &select.from[0].relation
    else {
        return None;
    };
    Some(name.to_string())
}

fn classify_model(query: &Query, model: &Model) -> ModelClassification {
    let authored_dependencies = dependency_calls(&model.query_sql);
    let mut logical_seen = false;
    let ctes = top_ctes(query)
        .iter()
        .map(|cte| {
            let dependencies = dependency_calls(&cte.query.to_string());
            let dependency_import = dependency_import(&cte.query);
            let kind = if dependencies.is_empty() {
                logical_seen = true;
                CteKind::Logical
            } else {
                let mut rejections: Vec<ImportRejection> = Vec::new();
                if dependencies.len() > 1 {
                    rejections.push(ImportRejection::MultipleDependencies);
                }
                if logical_seen {
                    rejections.push(ImportRejection::AfterLogical);
                }
                if !dependency_import {
                    rejections.push(ImportRejection::Transformation);
                }
                CteKind::Import {
                    dependencies,
                    rejections,
                }
            };
            CteClassification {
                name: cte.alias.name.value.clone(),
                position: location_position(cte.alias.name.span.start),
                dependency_import,
                kind,
            }
        })
        .collect::<Vec<_>>();

    let passthrough = model.references.len() == 1
        && authored_dependencies.len() == 1
        && ctes.len() == 1
        && ctes.first().is_some_and(|cte| {
            cte.dependency_import
                && sole_table_name(query).as_deref() == Some(cte.name.as_str())
                && root_select(query).is_some_and(|select| plain_select(select, true))
        });

    ModelClassification {
        authored_dependencies,
        ctes,
        passthrough,
    }
}

fn dependency_calls(source: &str) -> Vec<String> {
    let source = source.to_ascii_lowercase();
    let mut calls: Vec<String> = Vec::new();
    let mut cursor = 0;
    while cursor < source.len() {
        let tail = &source[cursor..];
        let next_ref = tail.find("__ref");
        let next_source = tail.find("__source");
        let Some(relative) = (match (next_ref, next_source) {
            (Some(left), Some(right)) => Some(left.min(right)),
            (Some(value), None) | (None, Some(value)) => Some(value),
            (None, None) => None,
        }) else {
            break;
        };
        let start = cursor + relative;
        let name_end = start
            + if source[start..].starts_with("__source") {
                "__source".len()
            } else {
                "__ref".len()
            };
        let arguments = source[name_end..].trim_start();
        if !arguments.starts_with('(') {
            cursor = name_end;
            continue;
        }
        let Some(relative_end) = source[start..].find(')') else {
            calls.push(source[start..].to_owned());
            break;
        };
        let end = start + relative_end + 1;
        calls.push(source[start..end].to_owned());
        cursor = end;
    }
    calls
}

fn import_ctes(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    let mut imported: Vec<String> = Vec::new();
    for cte in &parsed.classification.ctes {
        let CteKind::Import {
            dependencies,
            rejections,
        } = &cte.kind
        else {
            continue;
        };
        if dependencies.len() == 1 {
            imported.extend(dependencies.iter().cloned());
        }
        for rejection in rejections {
            let message = match rejection {
                ImportRejection::MultipleDependencies => {
                    format!("import CTE {:?} reads multiple dependencies", cte.name)
                }
                ImportRejection::AfterLogical => {
                    format!("import CTE {:?} appears after logical CTEs", cte.name)
                }
                ImportRejection::Transformation => {
                    format!("import CTE {:?} contains transformation logic", cte.name)
                }
            };
            faults.push(custom_fault!(
                parsed.model,
                rule,
                Some(&cte.position),
                message,
                None,
            ));
        }
    }
    let duplicate = parsed
        .classification
        .authored_dependencies
        .iter()
        .collect::<HashSet<_>>()
        .len()
        != parsed.classification.authored_dependencies.len();
    let mut authored_sorted = parsed.classification.authored_dependencies.clone();
    let mut imported_sorted = imported;
    authored_sorted.sort();
    imported_sorted.sort();
    if duplicate || authored_sorted != imported_sorted {
        faults.push(custom_fault!(
            parsed.model,
            rule,
            None,
            "each __ref/__source must appear once in its own top-level import CTE".into(),
            None,
        ));
    }
}

fn select_star(
    parsed: &ParsedModel<'_>,
    config: &PolicyConfig,
    rule: &RuleMetadata,
    faults: &FaultCollector,
) -> Result<(), String> {
    let mut builder = GlobSetBuilder::new();
    for entry in &config.select_star_allow {
        for pattern in &entry.paths {
            builder.add(Glob::new(pattern).map_err(|error| error.to_string())?);
        }
    }
    let allowed = builder
        .build()
        .map_err(|error| error.to_string())?
        .is_match(&parsed.model.relative_path);
    let mut import_positions: HashSet<(u64, u64)> = HashSet::new();
    for (cte, classified) in top_ctes(&parsed.query)
        .iter()
        .zip(&parsed.classification.ctes)
    {
        if classified.dependency_import {
            for value in stars_in_query(&cte.query) {
                import_positions.insert((value.line, value.column));
            }
        }
    }
    for query in all_queries(&parsed.query) {
        let Some(select) = root_select(query) else {
            continue;
        };
        let stars = stars_in_select(select);
        for at in stars {
            if import_positions.contains(&(at.line, at.column)) {
                continue;
            }
            let lone = select.projection.len() == 1;
            if allowed && lone {
                continue;
            }
            let remediation = (allowed && !lone).then(|| MIXED_STAR_REMEDIATION.into());
            faults.push(custom_fault!(
                parsed.model,
                rule,
                Some(&at),
                rule.message.clone(),
                remediation,
            ));
        }
    }
    Ok(())
}

#[derive(Clone)]
struct NameParts {
    domain: String,
    layer: String,
    source: Option<String>,
    is_view: bool,
}

fn parse_name(name: &str) -> Option<NameParts> {
    let parts: Vec<&str> = name.split("__").collect();
    if !(3..=4).contains(&parts.len()) {
        return None;
    }
    let layers = [
        "stg",
        "stg_v",
        "int_clean",
        "int_v",
        "int_enriched",
        "mart",
        "mart_v",
    ];
    if !valid_lower_name_token(parts[0])
        || !layers.contains(&parts[1])
        || !valid_lower_name_token(parts[2])
        || parts
            .get(3)
            .is_some_and(|value| !valid_lower_name_token(value))
    {
        return None;
    }
    Some(NameParts {
        domain: parts[0].into(),
        layer: parts[1].into(),
        source: parts.get(3).map(|value| (*value).into()),
        is_view: parts[1].ends_with("_v"),
    })
}

fn valid_lower_name_token(value: &str) -> bool {
    let mut bytes = value.bytes();
    bytes.next().is_some_and(|byte| byte.is_ascii_lowercase())
        && bytes.all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
}

fn view_marker(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    let Some(parts) = parse_name(&parsed.model.name) else {
        return;
    };
    let materialized_view = parsed
        .model
        .config
        .get("materialized")
        .and_then(serde_json::Value::as_str)
        == Some(VIEW_MATERIALIZATION);
    if parts.is_view != materialized_view {
        faults.push(fault(parsed.model, rule, None));
    }
}

fn layer_order(layer: &str) -> usize {
    match layer {
        "stg" | "stg_v" => 0,
        "int_clean" => 1,
        "int_v" | "int_enriched" => 2,
        _ => 3,
    }
}

fn forward_refs(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    let Some(current) = parse_name(&parsed.model.name) else {
        return;
    };
    for reference in &parsed.model.references {
        if reference.ref_kind != REFERENCE_KIND {
            continue;
        }
        if let Some(upstream) = parse_name(&reference.ref_name)
            && layer_order(&upstream.layer) > layer_order(&current.layer)
        {
            faults.push(custom_fault!(
                parsed.model,
                rule,
                None,
                format!(
                    "{} reaches forward from {} to {} via {}",
                    parsed.model.name, current.layer, upstream.layer, reference.ref_name
                ),
                None,
            ));
        }
    }
}

fn raw_qualified_tables(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    for query in all_queries(&parsed.query) {
        let Some(select) = root_select(query) else {
            continue;
        };
        for source in &select.from {
            qualified_table_factor(parsed.model, &source.relation, rule, faults);
            for join in &source.joins {
                qualified_table_factor(parsed.model, &join.relation, rule, faults);
            }
        }
    }
}

fn qualified_table_factor(
    model: &Model,
    factor: &TableFactor,
    rule: &RuleMetadata,
    faults: &FaultCollector,
) {
    let TableFactor::Table {
        name, args: None, ..
    } = factor
    else {
        return;
    };
    if name.0.len() > 1 {
        faults.push(custom_fault!(
            model,
            rule,
            Some(&position(name)),
            format!(
                "raw qualified table {:?} bypasses the SQLBuild graph",
                name.to_string()
            ),
            None,
        ));
    }
}

fn name_grammar(
    parsed: &ParsedModel<'_>,
    config: &PolicyConfig,
    rule: &RuleMetadata,
    faults: &FaultCollector,
) {
    if let Some(parts) = parse_name(&parsed.model.name) {
        if !config.domains.is_empty() && !config.domains.contains(&parts.domain) {
            faults.push(custom_fault!(
                parsed.model,
                rule,
                None,
                format!(
                    "model {:?} uses unknown domain {:?}",
                    parsed.model.name, parts.domain
                ),
                Some("Rename the model into a configured policy domain, or add this domain to policy.domains when it is an intentional project owner.".into()),
            ));
        }
        return;
    }
    let apparent = parsed.model.name.split("__").nth(1);
    let message = if apparent.is_some_and(|value| value.starts_with("int")) {
        format!(
            "model {:?} uses unsupported intermediate layer {:?}",
            parsed.model.name,
            apparent.unwrap_or_default()
        )
    } else {
        format!(
            "model {:?} does not follow <domain>__<layer>__<entity>[__<source>]",
            parsed.model.name
        )
    };
    faults.push(custom_fault!(parsed.model, rule, None, message, None));
}

fn folder_layer(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    let Some(parts) = parse_name(&parsed.model.name) else {
        return;
    };
    let expected: &[&str] = match parts.layer.as_str() {
        "stg" | "stg_v" => &["staging"],
        "int_clean" => &["intermediate", "clean"],
        "int_enriched" => &["intermediate", "enriched"],
        "int_v" => &["intermediate"],
        _ => &["mart"],
    };
    let path: Vec<&str> = parsed.model.relative_path.split('/').collect();
    let parent = &path[..path.len().saturating_sub(1)];
    if !parent
        .windows(expected.len())
        .any(|window| window == expected)
    {
        faults.push(custom_fault!(
            parsed.model,
            rule,
            None,
            format!(
                "{} model {:?} must live under a {}/ folder",
                parts.layer,
                parsed.model.name,
                expected.join("/")
            ),
            None,
        ));
    }
}

fn source_token_policy(
    parsed: &ParsedModel<'_>,
    config: &PolicyConfig,
    rule: &RuleMetadata,
    faults: &FaultCollector,
) {
    let mut tokens: Vec<String> = Vec::new();
    if let Some(source) = parse_name(&parsed.model.name).and_then(|parts| parts.source) {
        tokens.push(source);
    }
    tokens.extend(
        parsed
            .model
            .references
            .iter()
            .filter(|reference| reference.ref_kind != REFERENCE_KIND)
            .map(|reference| reference.ref_name.clone()),
    );
    let mut retired_token: Option<(&String, &String)> = None;
    for token in &tokens {
        if let Some(replacement) = config.retired_source_tokens.get(token) {
            retired_token = Some((token, replacement));
            break;
        }
    }
    if let Some((retired, replacement)) = retired_token {
        faults.push(custom_fault!(
            parsed.model,
            rule,
            None,
            format!(
                "model {:?} uses retired source token {:?}",
                parsed.model.name, retired
            ),
            Some(format!(
                "Rename the model's source token to {replacement:?}; update references at the same model path."
            )),
        ));
    } else if !config.approved_source_tokens.is_empty()
        && let Some(token) = tokens
            .iter()
            .find(|token| !config.approved_source_tokens.contains(token))
    {
        faults.push(custom_fault!(
                parsed.model,
                rule,
                None,
                format!(
                    "model {:?} uses unapproved source token {:?}",
                    parsed.model.name, token
                ),
                Some("Rename the source suffix to a token listed in policy.approved_source_tokens at this model path.".into()),
            ));
    }
}

fn reference_name_policy(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    for reference in &parsed.model.references {
        if reference.ref_kind == REFERENCE_KIND && parse_name(&reference.ref_name).is_none() {
            faults.push(custom_fault!(
                parsed.model,
                rule,
                None,
                format!(
                    "reference {:?} does not follow policy model grammar",
                    reference.ref_name
                ),
                Some("Rename the referenced model to <domain>__<layer>__<entity>[__<source>] and update this __ref at the current model path.".into()),
            ));
        }
    }
}

fn contract_required(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    if parsed
        .model
        .config
        .get("contract")
        .and_then(serde_json::Value::as_str)
        != Some(ENFORCED_CONTRACT)
    {
        faults.push(fault(parsed.model, rule, None));
    }
}

fn evaluate_naming_rules(
    parsed: &ParsedModel<'_>,
    selected: &BTreeMap<String, &RuleMetadata>,
    faults: &FaultCollector,
) {
    for column in &parsed.model.columns {
        let data_type = column.data_type.to_ascii_uppercase();
        let rule_and_message = if column.name.starts_with("is_")
            || column.name.starts_with("has_")
            || column.name.starts_with("can_")
        {
            (data_type != BOOLEAN_TYPE).then(|| {
                (
                    "SQBPC102",
                    format!(
                        "column {:?} implies BOOLEAN but is typed {data_type}",
                        column.name
                    ),
                )
            })
        } else if column.name.ends_with("_at")
            || column.name.ends_with("_ts")
            || column.name.ends_with("_timestamp")
        {
            (!data_type.contains(TIMESTAMP_TYPE)).then(|| {
                (
                    "SQBPC103",
                    format!(
                        "column {:?} implies a timestamp but is typed {data_type}",
                        column.name
                    ),
                )
            })
        } else if column.name.ends_with("_date") {
            (data_type != DATE_TYPE).then(|| {
                (
                    "SQBPC104",
                    format!(
                        "column {:?} implies DATE but is typed {data_type}",
                        column.name
                    ),
                )
            })
        } else {
            None
        };
        if let Some((code, message)) = rule_and_message
            && let Some(rule) = selected.get(code)
        {
            faults.push(custom_fault!(parsed.model, rule, None, message, None));
        }
    }
}

fn evaluate_literal_rules(
    parsed: &ParsedModel<'_>,
    selected: &BTreeMap<String, &RuleMetadata>,
    faults: &FaultCollector,
) {
    let facts = select_facts(&parsed.query);
    for comparison in facts.into_iter().flat_map(|select| select.comparisons) {
        if let Some(rule) = selected.get("SQBPD101") {
            let enum_column = comparison
                .columns
                .iter()
                .any(|name| parsed.model.enum_columns.contains(name));
            let bare_string = comparison
                .string_literals
                .iter()
                .any(|literal| parsed.model.authored_sql.contains(literal));
            let modified_controlled_column = comparison.modified_columns.iter().any(|column| {
                parsed.model.enum_columns.contains(&column.name)
                    && !column.qualifier.as_ref().is_some_and(|qualifier| {
                        comparison.source_context.relations.contains(qualifier)
                    })
                    && !(column.qualifier.is_none() && comparison.source_context.sole_relation)
            });
            if enum_column
                && (bare_string || modified_controlled_column || comparison.modified_string_literal)
            {
                faults.push(fault(parsed.model, rule, comparison.position.as_ref()));
            }
        }
        if let Some(rule) = selected.get("SQBPD102") {
            let magic = comparison.numeric_literals.iter().any(|literal| {
                !matches!(literal.as_str(), "-1" | "0" | "1")
                    && parsed.model.authored_sql.contains(literal)
            });
            if magic {
                faults.push(fault(parsed.model, rule, comparison.position.as_ref()));
            }
        }
    }
}

fn evaluate_test_rules(evaluation: TestRuleEvaluation<'_>) {
    if evaluation.parsed.classification.passthrough {
        return;
    }
    if let Some(rule) = evaluation.selected.get("SQBPT201") {
        let minimum = effective_threshold(&evaluation, "min_audits_per_model", 1);
        if evaluation.parsed.model.declared_audit_count < minimum {
            evaluation.faults.push(custom_fault!(
                evaluation.parsed.model,
                rule,
                None,
                format!(
                    "model {:?} has {} audits; {} required",
                    evaluation.parsed.model.name,
                    evaluation.parsed.model.declared_audit_count,
                    minimum
                ),
                None,
            ));
        }
    }
    if let Some(rule) = evaluation.selected.get("SQBPT202") {
        let minimum = effective_threshold(&evaluation, "min_tests_per_model", 1);
        if evaluation.parsed.model.targeting_test_count < minimum {
            evaluation.faults.push(custom_fault!(
                evaluation.parsed.model,
                rule,
                None,
                format!(
                    "model {:?} has {} tests; {} required",
                    evaluation.parsed.model.name,
                    evaluation.parsed.model.targeting_test_count,
                    minimum
                ),
                None,
            ));
        }
    }
}

fn effective_threshold(evaluation: &TestRuleEvaluation<'_>, name: &str, default: u32) -> u32 {
    let mut value = evaluation
        .config
        .thresholds
        .get(name)
        .copied()
        .unwrap_or(default);
    for entry in evaluation.threshold_overrides {
        if entry.matches(&evaluation.parsed.model.relative_path)
            && let Some(overridden) = entry.threshold(name)
        {
            value = overridden;
        }
    }
    value
}

pub(crate) fn resolve_threshold_overrides(
    config: &PolicyConfig,
) -> Result<Vec<ResolvedThresholdOverride>, String> {
    config
        .threshold_overrides
        .iter()
        .map(|entry| {
            let mut builder = GlobSetBuilder::new();
            for pattern in &entry.paths {
                builder.add(Glob::new(pattern).map_err(|error| error.to_string())?);
            }
            Ok(ResolvedThresholdOverride {
                matcher: builder.build().map_err(|error| error.to_string())?,
                thresholds: entry.thresholds.clone(),
            })
        })
        .collect()
}

fn duplicate_enums(request: &EvaluateRequest, rule: &RuleMetadata, faults: &FaultCollector) {
    let declarations = request.public_enums.iter().chain(
        request
            .models
            .iter()
            .flat_map(|model| model.enum_declarations.iter()),
    );
    let mut signatures: BTreeMap<String, &Declaration> = BTreeMap::new();
    for declaration in declarations {
        let mut members: Vec<_> = declaration
            .members
            .iter()
            .map(|member| (member.name.clone(), format!("{:?}", member.value)))
            .collect();
        members.sort();
        let signature = serde_json::to_string(&members).unwrap_or_default();
        if let Some(previous) = signatures.get(&signature) {
            faults.push(path_fault(
                &declaration.relative_path,
                rule,
                format!("enum {:?} duplicates {:?}", declaration.name, previous.name),
                rule.remediation.clone(),
            ));
        }
        signatures.insert(signature, declaration);
    }
}

fn declaration_domain_placement(
    request: &EvaluateRequest,
    config: &PolicyConfig,
    rule: &RuleMetadata,
    faults: &FaultCollector,
) {
    for declaration in request
        .public_enums
        .iter()
        .chain(request.public_constants.iter())
    {
        let parts: Vec<_> = declaration.relative_path.split('/').collect();
        let domain = (parts.len() >= DECLARATION_DOMAIN_COMPONENTS).then(|| parts[1]);
        if domain.is_some_and(|value| {
            config.domains.is_empty() || config.domains.contains(&value.into())
        }) {
            continue;
        }
        let expected = if config.domains.is_empty() {
            "<domain>".into()
        } else {
            config.domains.join("|")
        };
        let root = parts.first().copied().unwrap_or("declarations");
        faults.push(path_fault(
            &declaration.relative_path,
            rule,
            format!(
                "public declaration {:?} has no configured domain folder",
                declaration.name
            ),
            format!("Move this declaration under {root}/{expected}/ at this file path."),
        ));
    }
}

fn custom_rule_test_coverage(
    request: &EvaluateRequest,
    config: &PolicyConfig,
    policy: (&BTreeMap<String, &RuleMetadata>, &RuleMetadata),
    faults: &FaultCollector,
) {
    let (selected, rule) = policy;
    let minimum = config
        .thresholds
        .get("min_custom_rule_test_cases")
        .copied()
        .unwrap_or(1);
    if minimum == 0 {
        return;
    }
    for custom in &request.custom_rules {
        if !selected.contains_key(&custom.code) {
            continue;
        }
        if custom.test_case_count < minimum {
            faults.push(Fault {
                code: rule.code.clone(),
                path: custom.source.clone().unwrap_or_else(|| "policy".into()),
                line: custom.source_line.max(1),
                column: custom.source_column.max(1),
                message: format!(
                    "custom rule {} has {} harness cases; {} required",
                    custom.code, custom.test_case_count, minimum
                ),
                remediation: rule.remediation.clone(),
            });
        }
    }
}

fn all_queries(root: &Query) -> Vec<&Query> {
    fn collect_query<'a>(query: &'a Query, values: &mut Vec<&'a Query>) {
        values.push(query);
        if let Some(with) = &query.with {
            for cte in &with.cte_tables {
                collect_query(&cte.query, values);
            }
        }
        collect_set_expr(&query.body, values);
    }
    fn collect_set_expr<'a>(body: &'a SetExpr, values: &mut Vec<&'a Query>) {
        match body {
            SetExpr::Query(query) => collect_query(query, values),
            SetExpr::SetOperation { left, right, .. } => {
                collect_set_expr(left, values);
                collect_set_expr(right, values);
            }
            _ => {}
        }
    }
    let mut values: Vec<&Query> = Vec::new();
    collect_query(root, &mut values);
    values
}

fn stars_in_query(query: &Query) -> Vec<Position> {
    all_queries(query)
        .into_iter()
        .filter_map(root_select)
        .flat_map(stars_in_select)
        .collect()
}

fn stars_in_select(select: &Select) -> Vec<Position> {
    select
        .projection
        .iter()
        .filter_map(|item| match item {
            SelectItem::Wildcard(options) | SelectItem::QualifiedWildcard(_, options) => {
                Some(location_position(options.wildcard_token.0.span.start))
            }
            _ => None,
        })
        .collect()
}

fn select_facts(query: &Query) -> Vec<SelectFacts> {
    let source_imports = source_import_names(query);
    all_queries(query)
        .into_iter()
        .filter_map(root_select)
        .map(|select| {
            let source_context = select_source_context(select, &source_imports);
            let mut result = SelectFacts::default();
            for source in &select.from {
                for join in &source.joins {
                    if let Some(JoinConstraint::On(expr)) = join_constraint(&join.join_operator) {
                        comparison_facts(expr, &source_context, &mut result.comparisons);
                    }
                }
            }
            for item in &select.projection {
                match item {
                    SelectItem::UnnamedExpr(expression)
                    | SelectItem::ExprWithAlias {
                        expr: expression, ..
                    } => {
                        case_comparison_facts(expression, &source_context, &mut result.comparisons);
                    }
                    SelectItem::QualifiedWildcard(_, _) | SelectItem::Wildcard(_) => {}
                }
            }
            for expression in [
                select.selection.as_ref(),
                select.having.as_ref(),
                select.qualify.as_ref(),
            ]
            .into_iter()
            .flatten()
            {
                comparison_facts(expression, &source_context, &mut result.comparisons);
            }
            result
        })
        .collect()
}

fn source_import_names(query: &Query) -> BTreeSet<String> {
    top_ctes(query)
        .iter()
        .filter(|cte| {
            dependency_import(&cte.query)
                && root_select(&cte.query).is_some_and(|select| {
                    select.from.len() == 1
                        && select.from[0].joins.is_empty()
                        && dependency_name(&select.from[0].relation).as_deref() == Some("__source")
                })
        })
        .map(|cte| cte.alias.name.value.to_ascii_lowercase())
        .collect()
}

fn select_source_context(select: &Select, source_imports: &BTreeSet<String>) -> SourceContext {
    let mut relations: BTreeSet<String> = BTreeSet::new();
    for source in &select.from {
        if let Some(name) = source_relation_name(&source.relation, source_imports) {
            relations.insert(name);
        }
        for join in &source.joins {
            if let Some(name) = source_relation_name(&join.relation, source_imports) {
                relations.insert(name);
            }
        }
    }
    let sole_relation = select.from.len() == 1
        && select.from[0].joins.is_empty()
        && source_relation_name(&select.from[0].relation, source_imports).is_some();
    SourceContext {
        relations,
        sole_relation,
    }
}

fn source_relation_name(factor: &TableFactor, source_imports: &BTreeSet<String>) -> Option<String> {
    let TableFactor::Table {
        name, args, alias, ..
    } = factor
    else {
        return None;
    };
    let relation_name = name.0.last()?.as_ident()?.value.to_ascii_lowercase();
    if args.is_none() && !source_imports.contains(&relation_name) {
        return None;
    }
    if args.is_some() && dependency_name(factor).as_deref() != Some("__source") {
        return None;
    }
    Some(
        alias
            .as_ref()
            .map_or(relation_name, |value| value.name.value.to_ascii_lowercase()),
    )
}

fn join_constraint(operator: &JoinOperator) -> Option<&JoinConstraint> {
    match operator {
        JoinOperator::Join(value)
        | JoinOperator::Inner(value)
        | JoinOperator::Left(value)
        | JoinOperator::LeftOuter(value)
        | JoinOperator::Right(value)
        | JoinOperator::RightOuter(value)
        | JoinOperator::FullOuter(value)
        | JoinOperator::Semi(value)
        | JoinOperator::LeftSemi(value)
        | JoinOperator::RightSemi(value)
        | JoinOperator::Anti(value)
        | JoinOperator::LeftAnti(value)
        | JoinOperator::RightAnti(value)
        | JoinOperator::StraightJoin(value)
        | JoinOperator::AsOf {
            constraint: value, ..
        } => Some(value),
        _ => None,
    }
}

fn numeric_value(expression: &Expr) -> Option<String> {
    match expression {
        Expr::Value(value) => match &value.value {
            Value::Number(value, _) => Some(value.to_string()),
            _ => None,
        },
        Expr::UnaryOp { op, expr } if op.to_string() == NEGATION_OPERATOR => {
            numeric_value(expr).map(|value| format!("-{value}"))
        }
        _ => None,
    }
}

fn comparison_facts(root: &Expr, source_context: &SourceContext, output: &mut Vec<ComparisonFact>) {
    struct Comparisons<'a> {
        source_context: &'a SourceContext,
        output: &'a mut Vec<ComparisonFact>,
    }
    impl Visitor for Comparisons<'_> {
        type Break = ();
        fn pre_visit_expr(&mut self, expression: &Expr) -> ControlFlow<Self::Break> {
            if let Expr::BinaryOp { op, .. } = expression
                && matches!(
                    op,
                    BinaryOperator::Eq
                        | BinaryOperator::NotEq
                        | BinaryOperator::Gt
                        | BinaryOperator::GtEq
                        | BinaryOperator::Lt
                        | BinaryOperator::LtEq
                )
            {
                self.output
                    .push(comparison_fact(expression, self.source_context));
            }
            ControlFlow::Continue(())
        }
    }
    let mut visitor = Comparisons {
        source_context,
        output,
    };
    let _ = root.visit(&mut visitor);
}

fn case_comparison_facts(
    root: &Expr,
    source_context: &SourceContext,
    output: &mut Vec<ComparisonFact>,
) {
    struct CaseComparisons<'a> {
        source_context: &'a SourceContext,
        output: &'a mut Vec<ComparisonFact>,
    }
    impl Visitor for CaseComparisons<'_> {
        type Break = ();

        fn pre_visit_expr(&mut self, expression: &Expr) -> ControlFlow<Self::Break> {
            if let Expr::Case {
                operand,
                conditions,
                ..
            } = expression
            {
                if let Some(value) = operand {
                    comparison_facts(value, self.source_context, self.output);
                }
                for condition in conditions {
                    comparison_facts(&condition.condition, self.source_context, self.output);
                }
            }
            ControlFlow::Continue(())
        }
    }
    let mut visitor = CaseComparisons {
        source_context,
        output,
    };
    let _ = root.visit(&mut visitor);
}

fn comparison_fact(root: &Expr, source_context: &SourceContext) -> ComparisonFact {
    struct Values {
        fact: ComparisonFact,
    }
    impl Visitor for Values {
        type Break = ();
        fn pre_visit_expr(&mut self, expression: &Expr) -> ControlFlow<Self::Break> {
            match expression {
                Expr::Identifier(value) => {
                    self.fact.columns.insert(value.value.clone());
                }
                Expr::CompoundIdentifier(values) => {
                    if let Some(value) = values.last() {
                        self.fact.columns.insert(value.value.clone());
                    }
                }
                Expr::Value(value) => match &value.value {
                    Value::Number(number, _) => {
                        self.fact.numeric_literals.push(number.to_string());
                    }
                    Value::SingleQuotedString(_)
                    | Value::DoubleQuotedString(_)
                    | Value::TripleSingleQuotedString(_)
                    | Value::TripleDoubleQuotedString(_)
                    | Value::EscapedStringLiteral(_)
                    | Value::UnicodeStringLiteral(_)
                    | Value::NationalStringLiteral(_) => {
                        self.fact.string_literals.push(expression.to_string());
                    }
                    _ => {}
                },
                Expr::UnaryOp { op, expr } if op.to_string() == NEGATION_OPERATOR => {
                    if let Some(number) = numeric_value(expr) {
                        self.fact.numeric_literals.push(format!("-{number}"));
                    }
                }
                _ => {}
            }
            ControlFlow::Continue(())
        }
    }
    let mut visitor = Values {
        fact: ComparisonFact {
            position: Some(position(root)),
            source_context: source_context.clone(),
            ..ComparisonFact::default()
        },
    };
    let _ = root.visit(&mut visitor);
    if let Expr::BinaryOp { left, right, .. } = root {
        for operand in [left.as_ref(), right.as_ref()] {
            if direct_column(operand).is_none() {
                visitor.fact.modified_columns.extend(column_facts(operand));
            }
            if direct_string_literal(operand).is_none() && contains_string_literal(operand) {
                visitor.fact.modified_string_literal = true;
            }
        }
    }
    visitor.fact
}

fn direct_column(expression: &Expr) -> Option<ColumnFact> {
    match unwrap_nested(expression) {
        Expr::Identifier(value) => Some(ColumnFact {
            name: value.value.clone(),
            qualifier: None,
        }),
        Expr::CompoundIdentifier(values) => {
            let name = values.last()?.value.clone();
            let qualifier = values
                .get(values.len().checked_sub(2)?)
                .map(|value| value.value.to_ascii_lowercase());
            Some(ColumnFact { name, qualifier })
        }
        _ => None,
    }
}

fn direct_string_literal(expression: &Expr) -> Option<String> {
    let Expr::Value(value) = unwrap_nested(expression) else {
        return None;
    };
    matches!(
        value.value,
        Value::SingleQuotedString(_)
            | Value::DoubleQuotedString(_)
            | Value::TripleSingleQuotedString(_)
            | Value::TripleDoubleQuotedString(_)
            | Value::EscapedStringLiteral(_)
            | Value::UnicodeStringLiteral(_)
            | Value::NationalStringLiteral(_)
    )
    .then(|| expression.to_string())
}

fn unwrap_nested(mut expression: &Expr) -> &Expr {
    while let Expr::Nested(value) = expression {
        expression = value;
    }
    expression
}

fn column_facts(root: &Expr) -> BTreeSet<ColumnFact> {
    struct Columns {
        values: BTreeSet<ColumnFact>,
    }
    impl Visitor for Columns {
        type Break = ();
        fn pre_visit_expr(&mut self, expression: &Expr) -> ControlFlow<Self::Break> {
            if let Some(column) = direct_column(expression) {
                self.values.insert(column);
            }
            ControlFlow::Continue(())
        }
    }
    let mut visitor = Columns {
        values: BTreeSet::new(),
    };
    let _ = root.visit(&mut visitor);
    visitor.values
}

fn contains_string_literal(root: &Expr) -> bool {
    struct Strings {
        found: bool,
    }
    impl Visitor for Strings {
        type Break = ();
        fn pre_visit_expr(&mut self, expression: &Expr) -> ControlFlow<Self::Break> {
            if direct_string_literal(expression).is_some() {
                self.found = true;
                return ControlFlow::Break(());
            }
            ControlFlow::Continue(())
        }
    }
    let mut visitor = Strings { found: false };
    let _ = root.visit(&mut visitor);
    visitor.found
}
