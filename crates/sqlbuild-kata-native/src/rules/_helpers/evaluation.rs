use crate::constants::{
    BOOLEAN_TYPE, DATE_TYPE, DECLARATION_DOMAIN_COMPONENTS, ENFORCED_CONTRACT,
    MEANINGLESS_FINAL_NAME, NEGATION_OPERATOR, REFERENCE_KIND, SQL_AS_KEYWORD_LENGTH,
    TIMESTAMP_TYPE, TRIVIAL_JOIN_VALUE, VIEW_MATERIALIZATION,
};
use crate::models::{Declaration, EvaluateRequest, Fault, KataConfig, Model, RuleMetadata};
use crate::rules::models::{FaultCollector, ModelEvaluationRequest};
use globset::{Glob, GlobSetBuilder};
use sqlparser::ast::{
    BinaryOperator, Expr, GroupByExpr, JoinConstraint, JoinOperator, Query, Select, SelectItem,
    SetExpr, SetQuantifier, Spanned, TableFactor, Value, Visit, Visitor,
};
use sqlparser::dialect::GenericDialect;
use sqlparser::parser::Parser;
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::ops::ControlFlow;

const MIXED_STAR_REMEDIATION: &str = "SELECT *, a, b mixes a passthrough star with derived columns. The * exemption permits a lone SELECT * only. Move a and b into an earlier CTE so they are computed upstream, leaving the final select a pure SELECT *. If you need those columns in the output, drop the * exemption and enumerate every column explicitly.";

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
}

#[derive(Default)]
struct SelectFacts {
    position: Option<Position>,
    from_count: usize,
    joins: Vec<JoinFact>,
    comparisons: Vec<ComparisonFact>,
}

enum JoinFact {
    Cross,
    MissingKey,
    TriviallyTrue,
    Keyed,
}

struct ParsedModel<'a> {
    query: Query,
    model: &'a Model,
}

pub(crate) fn evaluate_model(request: ModelEvaluationRequest<'_>) -> Result<Vec<Fault>, String> {
    let ModelEvaluationRequest {
        model,
        config,
        selected,
        request,
        is_anchor,
    } = request;
    let mut statements = Parser::parse_sql(&GenericDialect {}, &model.query_sql)
        .map_err(|error| format!("could not parse {} for kata: {error}", model.relative_path))?;
    if statements.len() != 1 {
        return Err(format!(
            "could not parse {} for kata: expected one statement",
            model.relative_path
        ));
    }
    let statement = statements.remove(0);
    let sqlparser::ast::Statement::Query(query) = statement else {
        return Err(format!(
            "could not parse {} for kata: expected a query",
            model.relative_path
        ));
    };
    let parsed = ParsedModel {
        query: *query,
        model,
    };
    let metadata = |code: &str| selected.get(code).copied();
    let faults = FaultCollector::default();

    if let Some(rule) = metadata("SQBKS000") {
        comment_discipline(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKS001") {
        cte_only(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKS002") {
        terminal_select(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKS101") {
        import_ctes(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKS201") {
        select_star(&parsed, config, rule, &faults)?;
    }
    if let Some(rule) = metadata("SQBKS202") {
        positional_set_star(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKS301") {
        nested_ctes(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKS302") {
        recursive_ctes(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKS401") {
        view_marker(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKS501") {
        meaningless_cte_names(&parsed, config, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKL001") {
        forward_refs(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKL101") {
        raw_qualified_tables(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKR001") {
        name_grammar(&parsed, config, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKR002") {
        folder_layer(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKR201") {
        source_token_policy(&parsed, config, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKR301") {
        reference_name_policy(&parsed, rule, &faults);
    }
    if let Some(rule) = metadata("SQBKR401") {
        contract_required(&parsed, rule, &faults);
    }
    evaluate_join_rules(&parsed, selected, &faults);
    evaluate_naming_rules(&parsed, selected, &faults);
    evaluate_literal_rules(&parsed, selected, &faults);
    evaluate_test_rules(&parsed, config, selected, &faults);

    if is_anchor {
        if let Some(rule) = metadata("SQBKH101") {
            duplicate_enums(request, rule, &faults);
        }
        if let Some(rule) = metadata("SQBKH201") {
            declaration_domain_placement(request, config, rule, &faults);
        }
        if let Some(rule) = metadata("SQBKX201") {
            custom_rule_test_coverage(request, config, (selected, rule), &faults);
        }
    }
    Ok(faults.into_inner())
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

fn comment_discipline(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    let mut previous_code = String::new();
    let mut cte_head_comment_seen = false;
    for (index, line) in parsed.model.query_sql.lines().enumerate() {
        let stripped = line.trim();
        let is_comment = stripped.starts_with("--") || stripped.starts_with("/*");
        if is_comment {
            let at_head = opens_cte(&previous_code);
            if !at_head || cte_head_comment_seen {
                faults.push(fault(
                    parsed.model,
                    rule,
                    Some(&Position {
                        line: (index + 1) as u64,
                        column: 1,
                    }),
                ));
            }
            if at_head {
                cte_head_comment_seen = true;
            }
            continue;
        }
        if line.contains("--") || line.contains("/*") {
            faults.push(fault(
                parsed.model,
                rule,
                Some(&Position {
                    line: (index + 1) as u64,
                    column: 1,
                }),
            ));
        }
        if !stripped.is_empty() {
            previous_code = stripped.into();
            cte_head_comment_seen = false;
        }
    }
}

fn opens_cte(source: &str) -> bool {
    let Some(before_parenthesis) = source.trim_end().strip_suffix('(') else {
        return false;
    };
    let before_parenthesis = before_parenthesis.trim_end();
    if before_parenthesis.len() < SQL_AS_KEYWORD_LENGTH
        || !before_parenthesis[before_parenthesis.len() - SQL_AS_KEYWORD_LENGTH..]
            .eq_ignore_ascii_case("as")
    {
        return false;
    }
    let before_as = &before_parenthesis[..before_parenthesis.len() - SQL_AS_KEYWORD_LENGTH];
    before_as
        .split_whitespace()
        .next_back()
        .is_some_and(valid_name_token)
}

fn valid_name_token(value: &str) -> bool {
    let mut characters = value.chars();
    characters
        .next()
        .is_some_and(|character| character.is_ascii_alphabetic() || character == '_')
        && characters.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

fn cte_only(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    let Some(select) = root_select(&parsed.query) else {
        faults.push(fault(parsed.model, rule, None));
        return;
    };
    if top_ctes(&parsed.query).is_empty()
        || select.selection.is_some()
        || !group_by_empty(&select.group_by)
        || select.from.iter().any(|source| !source.joins.is_empty())
    {
        faults.push(fault(parsed.model, rule, None));
    }
}

fn terminal_select(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    let ctes = top_ctes(&parsed.query);
    let Some(last) = ctes.last() else {
        return;
    };
    if sole_table_name(&parsed.query).as_deref() != Some(last.alias.name.value.as_str()) {
        faults.push(custom_fault!(
            parsed.model,
            rule,
            None,
            "terminal SELECT must read from the final top-level CTE".into(),
            None,
        ));
    } else if !root_select(&parsed.query).is_some_and(|select| plain_select(select, true)) {
        faults.push(custom_fault!(
            parsed.model,
            rule,
            None,
            "terminal SELECT contains logic outside the final CTE".into(),
            None,
        ));
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
    let authored = dependency_calls(&parsed.model.query_sql);
    let mut imported: Vec<String> = Vec::new();
    let mut logical_seen = false;
    for cte in top_ctes(&parsed.query) {
        let body = cte.query.to_string();
        let references = dependency_calls(&body);
        if references.is_empty() {
            logical_seen = true;
            continue;
        }
        let at = location_position(cte.alias.name.span.start);
        if references.len() > 1 {
            faults.push(custom_fault!(
                parsed.model,
                rule,
                Some(&at),
                format!(
                    "import CTE {:?} reads multiple dependencies",
                    cte.alias.name.value
                ),
                None,
            ));
        }
        if references.len() == 1 {
            imported.extend(references);
            if logical_seen {
                faults.push(custom_fault!(
                    parsed.model,
                    rule,
                    Some(&at),
                    format!(
                        "import CTE {:?} appears after logical CTEs",
                        cte.alias.name.value
                    ),
                    None,
                ));
            }
            if !dependency_import(&cte.query) {
                faults.push(custom_fault!(
                    parsed.model,
                    rule,
                    Some(&at),
                    format!(
                        "import CTE {:?} contains transformation logic",
                        cte.alias.name.value
                    ),
                    None,
                ));
            }
        }
    }
    let duplicate = authored.iter().collect::<HashSet<_>>().len() != authored.len();
    let mut authored_sorted = authored;
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
    config: &KataConfig,
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
    for cte in top_ctes(&parsed.query) {
        if dependency_import(&cte.query) {
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

fn positional_set_star(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    fn visit(model: &Model, body: &SetExpr, rule: &RuleMetadata, faults: &FaultCollector) {
        match body {
            SetExpr::SetOperation {
                set_quantifier,
                left,
                right,
                ..
            } => {
                let by_name = matches!(
                    set_quantifier,
                    SetQuantifier::ByName
                        | SetQuantifier::AllByName
                        | SetQuantifier::DistinctByName
                );
                if !by_name && (set_expr_has_star(left) || set_expr_has_star(right)) {
                    faults.push(fault(model, rule, None));
                }
                visit(model, left, rule, faults);
                visit(model, right, rule, faults);
            }
            SetExpr::Query(query) => visit(model, &query.body, rule, faults),
            _ => {}
        }
    }
    for query in all_queries(&parsed.query) {
        visit(parsed.model, &query.body, rule, faults);
    }
}

fn nested_ctes(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    if all_queries(&parsed.query)
        .iter()
        .filter(|query| query.with.is_some())
        .count()
        > usize::from(parsed.query.with.is_some())
    {
        faults.push(fault(parsed.model, rule, None));
    }
}

fn recursive_ctes(parsed: &ParsedModel<'_>, rule: &RuleMetadata, faults: &FaultCollector) {
    if parsed
        .query
        .with
        .as_ref()
        .is_some_and(|with| with.recursive)
    {
        faults.push(fault(parsed.model, rule, None));
    }
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

fn meaningless_cte_names(
    parsed: &ParsedModel<'_>,
    config: &KataConfig,
    rule: &RuleMetadata,
    faults: &FaultCollector,
) {
    let built_in = [
        "data",
        "result",
        "results",
        "output",
        "rows",
        "records",
        "stuff",
        "things",
        "working",
        "scratch",
        "misc",
        "temp_table",
        "tmp_table",
    ];
    for cte in top_ctes(&parsed.query) {
        let name = cte.alias.name.value.to_ascii_lowercase();
        if matches!(name.as_str(), "final" | "final_cte")
            || config.cte_name_whitelist.contains(&name)
            || name.ends_with("_base")
        {
            continue;
        }
        if built_in.contains(&name.as_str())
            || config.cte_name_denylist.contains(&name)
            || meaningless_generated_name(&name)
        {
            faults.push(custom_fault!(
                parsed.model,
                rule,
                Some(&location_position(cte.alias.name.span.start)),
                format!("CTE {name:?} has a meaningless name"),
                None,
            ));
        }
    }
}

fn meaningless_generated_name(name: &str) -> bool {
    if name == MEANINGLESS_FINAL_NAME {
        return true;
    }
    if let Some(suffix) = name.strip_prefix("final") {
        return !suffix.is_empty() && suffix.bytes().all(|byte| byte.is_ascii_digit());
    }
    for prefix in [
        "cte", "tmp", "temp", "t", "tbl", "table", "q", "query", "sub", "subquery", "step", "s",
    ] {
        if name
            .strip_prefix(prefix)
            .is_some_and(|suffix| suffix.bytes().all(|byte| byte.is_ascii_digit()))
        {
            return true;
        }
    }
    let letter_count = name.bytes().take_while(u8::is_ascii_lowercase).count();
    (1..=2).contains(&letter_count)
        && name[letter_count..]
            .bytes()
            .all(|byte| byte.is_ascii_digit())
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
        if let Some(upstream) = parse_name(&reference.ref_name) {
            if layer_order(&upstream.layer) > layer_order(&current.layer) {
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
    config: &KataConfig,
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
                Some("Rename the model into a configured kata domain, or add this domain to kata.domains when it is an intentional project owner.".into()),
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
    config: &KataConfig,
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
    } else if !config.approved_source_tokens.is_empty() {
        if let Some(token) = tokens
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
                Some("Rename the source suffix to a token listed in kata.approved_source_tokens at this model path.".into()),
            ));
        }
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
                    "reference {:?} does not follow kata model grammar",
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

fn evaluate_join_rules(
    parsed: &ParsedModel<'_>,
    selected: &BTreeMap<String, &RuleMetadata>,
    faults: &FaultCollector,
) {
    let facts = select_facts(&parsed.query);
    for select in facts {
        if select.from_count > 1 {
            if let Some(rule) = selected.get("SQBKJ001") {
                faults.push(fault(parsed.model, rule, select.position.as_ref()));
            }
        }
        for join in select.joins {
            match join {
                JoinFact::Cross => {
                    if let Some(rule) = selected.get("SQBKJ002") {
                        faults.push(fault(parsed.model, rule, select.position.as_ref()));
                    }
                }
                JoinFact::MissingKey | JoinFact::TriviallyTrue => {
                    if let Some(rule) = selected.get("SQBKJ101") {
                        faults.push(fault(parsed.model, rule, select.position.as_ref()));
                    }
                }
                JoinFact::Keyed => {}
            }
        }
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
                    "SQBKN001",
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
                    "SQBKN002",
                    format!(
                        "column {:?} implies a timestamp but is typed {data_type}",
                        column.name
                    ),
                )
            })
        } else if column.name.ends_with("_date") {
            (data_type != DATE_TYPE).then(|| {
                (
                    "SQBKN003",
                    format!(
                        "column {:?} implies DATE but is typed {data_type}",
                        column.name
                    ),
                )
            })
        } else {
            None
        };
        if let Some((code, message)) = rule_and_message {
            if let Some(rule) = selected.get(code) {
                faults.push(custom_fault!(parsed.model, rule, None, message, None));
            }
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
        if let Some(rule) = selected.get("SQBKH001") {
            let enum_column = comparison
                .columns
                .iter()
                .any(|name| parsed.model.enum_columns.contains(name));
            let bare_string = comparison
                .string_literals
                .iter()
                .any(|literal| parsed.model.authored_sql.contains(literal));
            if enum_column && bare_string {
                faults.push(fault(parsed.model, rule, comparison.position.as_ref()));
            }
        }
        if let Some(rule) = selected.get("SQBKH002") {
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

fn is_passthrough(parsed: &ParsedModel<'_>) -> bool {
    let ctes = top_ctes(&parsed.query);
    parsed.model.references.len() == 1
        && ctes.len() == 1
        && dependency_calls(&parsed.model.query_sql).len() == 1
        && dependency_import(&ctes[0].query)
        && sole_table_name(&parsed.query).as_deref() == Some(ctes[0].alias.name.value.as_str())
        && root_select(&parsed.query).is_some_and(|select| plain_select(select, true))
}

fn evaluate_test_rules(
    parsed: &ParsedModel<'_>,
    config: &KataConfig,
    selected: &BTreeMap<String, &RuleMetadata>,
    faults: &FaultCollector,
) {
    if is_passthrough(parsed) {
        return;
    }
    if let Some(rule) = selected.get("SQBKX001") {
        let minimum = config
            .thresholds
            .get("min_audits_per_model")
            .copied()
            .unwrap_or(1);
        if parsed.model.declared_audit_count < minimum {
            faults.push(custom_fault!(
                parsed.model,
                rule,
                None,
                format!(
                    "model {:?} has {} audits; {} required",
                    parsed.model.name, parsed.model.declared_audit_count, minimum
                ),
                None,
            ));
        }
    }
    if let Some(rule) = selected.get("SQBKX002") {
        let minimum = config
            .thresholds
            .get("min_tests_per_model")
            .copied()
            .unwrap_or(1);
        if parsed.model.targeting_test_count < minimum {
            faults.push(custom_fault!(
                parsed.model,
                rule,
                None,
                format!(
                    "model {:?} has {} tests; {} required",
                    parsed.model.name, parsed.model.targeting_test_count, minimum
                ),
                Some(test_remediation(parsed.model)),
            ));
        }
    }
}

fn test_remediation(model: &Model) -> String {
    let mock = model.references.first().map_or_else(
        || "__ref__upstream_model".into(),
        |reference| format!("__{}__{}", reference.ref_kind, reference.ref_name),
    );
    let example = format!(
        "TEST();\n\nWITH\n{mock} AS (\n  SELECT 1 AS input_id, 2 AS input_value\n),\n__expected__{} AS (\n  SELECT 1 AS output_id, 4 AS transformed_value\n)\nSELECT 1",
        model.name
    );
    format!(
        "Add a SQL unit test that mocks each real import and asserts concrete transformed rows, for example:\n\n{example}\n\nChoose input rows that exercise this model's actual filter, join, aggregation, or mapping. Do not merely assert that inputs survive unchanged or re-derive expected values with the model's own logic. Prove the test is failable: temporarily perturb the model logic or expected value, confirm the test fails, then revert the mutation."
    )
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
    config: &KataConfig,
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
    config: &KataConfig,
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
            faults.push(path_fault(
                custom.source.as_deref().unwrap_or("kata"),
                rule,
                format!(
                    "custom rule {} has {} harness cases; {} required",
                    custom.code, custom.test_case_count, minimum
                ),
                rule.remediation.clone(),
            ));
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

fn set_expr_has_star(body: &SetExpr) -> bool {
    match body {
        SetExpr::Select(select) => !stars_in_select(select).is_empty(),
        SetExpr::Query(query) => !stars_in_query(query).is_empty(),
        SetExpr::SetOperation { left, right, .. } => {
            set_expr_has_star(left) || set_expr_has_star(right)
        }
        _ => false,
    }
}

fn select_facts(query: &Query) -> Vec<SelectFacts> {
    all_queries(query)
        .into_iter()
        .filter_map(root_select)
        .map(|select| {
            let mut result = SelectFacts {
                position: Some(location_position(select.select_token.0.span.start)),
                from_count: select.from.len(),
                ..SelectFacts::default()
            };
            for source in &select.from {
                for join in &source.joins {
                    result.joins.push(join_fact(&join.join_operator));
                    if let Some(JoinConstraint::On(expr)) = join_constraint(&join.join_operator) {
                        comparison_facts(expr, &mut result.comparisons);
                    }
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
                comparison_facts(expression, &mut result.comparisons);
            }
            result
        })
        .collect()
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

fn join_fact(operator: &JoinOperator) -> JoinFact {
    if matches!(operator, JoinOperator::CrossJoin) {
        return JoinFact::Cross;
    }
    let Some(constraint) = join_constraint(operator) else {
        return JoinFact::Keyed;
    };
    match constraint {
        JoinConstraint::None => JoinFact::MissingKey,
        JoinConstraint::On(Expr::BinaryOp {
            left,
            op: BinaryOperator::Eq,
            right,
        }) if numeric_value(left).as_deref() == Some(TRIVIAL_JOIN_VALUE)
            && numeric_value(right).as_deref() == Some(TRIVIAL_JOIN_VALUE) =>
        {
            JoinFact::TriviallyTrue
        }
        _ => JoinFact::Keyed,
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

fn comparison_facts(root: &Expr, output: &mut Vec<ComparisonFact>) {
    struct Comparisons<'a> {
        output: &'a mut Vec<ComparisonFact>,
    }
    impl Visitor for Comparisons<'_> {
        type Break = ();
        fn pre_visit_expr(&mut self, expression: &Expr) -> ControlFlow<Self::Break> {
            if let Expr::BinaryOp { op, .. } = expression {
                if matches!(
                    op,
                    BinaryOperator::Eq
                        | BinaryOperator::NotEq
                        | BinaryOperator::Gt
                        | BinaryOperator::GtEq
                        | BinaryOperator::Lt
                        | BinaryOperator::LtEq
                ) {
                    self.output.push(comparison_fact(expression));
                }
            }
            ControlFlow::Continue(())
        }
    }
    let mut visitor = Comparisons { output };
    let _ = root.visit(&mut visitor);
}

fn comparison_fact(root: &Expr) -> ComparisonFact {
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
            ..ComparisonFact::default()
        },
    };
    let _ = root.visit(&mut visitor);
    visitor.fact
}
