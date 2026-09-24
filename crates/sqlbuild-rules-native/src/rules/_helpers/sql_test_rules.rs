use crate::compiler::main::sql_test_fixture_facts::fixture_facts;
use crate::models::{
    DeclarationKind, EvaluateRequest, Fault, Model, ResourceKind, RuleMetadata, RulesConfig,
    ScopeResource, SqlScenarioFact, SqlTestCteFact, SqlTestFact, SqlTestMode,
};
use crate::rules::_helpers::evaluation::{
    dependency_name, group_by_empty, normalize_rules_sql, parse_rule_statements, unwrap_nested,
};
use crate::rules::models::ProjectEvaluationRequest;
use sqlparser::ast::{
    BinaryOperator, Expr, FunctionArg, FunctionArgExpr, LimitClause, Query, Select, SetExpr,
    Statement, TableFactor, Value, Visit, Visitor,
};
use std::collections::BTreeMap;
use std::ops::ControlFlow;
use std::path::Path;

const UNIT_ROOT: &str = "tests/unit";
const SCENARIO_ROOT: &str = "tests/scenarios";
const EMPTY_INPUT_RULE_CODE: &str = "SQBRTEST203";
const ALLOWED_TESTS_OPTION: &str = "allowed_tests";
const PROJECT_CONFIG_PATH: &str = "sqlbuild_project.toml";

pub(crate) fn evaluate_project(
    evaluation: ProjectEvaluationRequest<'_>,
) -> Result<Vec<Fault>, String> {
    let mut faults: Vec<Fault> = Vec::new();
    let mut tests: Vec<&SqlTestFact> = evaluation.request.sql_tests.iter().collect();
    tests.sort_by(|left, right| {
        (&left.source_path, left.block_index).cmp(&(&right.source_path, right.block_index))
    });
    let mut scenarios: Vec<&SqlScenarioFact> = evaluation.request.sql_scenarios.iter().collect();
    scenarios.sort_by(|left, right| left.source_path.cmp(&right.source_path));

    if let Some(rule) = evaluation.selected.get("SQBRTEST101") {
        faults.extend(canonical_roots(rule, &tests, &scenarios));
    }
    if let Some(rule) = evaluation.selected.get("SQBRTEST102") {
        faults.extend(filenames(rule, &evaluation, &tests, &scenarios));
    }
    if let Some(rule) = evaluation.selected.get("SQBRTEST103") {
        faults.extend(mirroring(rule, &evaluation, &tests));
    }
    if let Some(rule) = evaluation.selected.get("SQBRTEST104") {
        faults.extend(structured_names(rule, &evaluation, &tests));
    }
    if let Some(rule) = evaluation.selected.get("SQBRTEST105") {
        faults.extend(scenario_descriptions(rule, &scenarios));
    }
    if let Some(rule) = evaluation.selected.get(EMPTY_INPUT_RULE_CODE) {
        faults.extend(empty_input_only_faults(
            rule,
            &evaluation.request.config,
            &tests,
        ));
    }
    Ok(faults)
}

fn canonical_roots(
    rule: &RuleMetadata,
    tests: &[&SqlTestFact],
    scenarios: &[&SqlScenarioFact],
) -> Vec<Fault> {
    let mut faults: Vec<Fault> = Vec::new();
    for test in tests {
        if test.ownership_root != UNIT_ROOT || !is_beneath(&test.source_path, UNIT_ROOT) {
            faults.push(path_fault(
                rule,
                &test.source_path,
                format!(
                    "unit test block {} is outside the canonical {UNIT_ROOT}/ root",
                    test.block_index
                ),
                format!("Move this unit test beneath {UNIT_ROOT}/."),
            ));
        }
    }
    for scenario in scenarios {
        if scenario.ownership_root != SCENARIO_ROOT
            || !is_beneath(&scenario.source_path, SCENARIO_ROOT)
        {
            faults.push(path_fault(
                rule,
                &scenario.source_path,
                format!("scenario is outside the canonical {SCENARIO_ROOT}/ root"),
                format!("Move this scenario beneath {SCENARIO_ROOT}/."),
            ));
        }
    }
    faults
}

fn filenames(
    rule: &RuleMetadata,
    evaluation: &ProjectEvaluationRequest<'_>,
    tests: &[&SqlTestFact],
    scenarios: &[&SqlScenarioFact],
) -> Vec<Fault> {
    let mut faults: Vec<Fault> = Vec::new();
    for test in tests {
        let stem = file_stem(&test.source_path);
        let allowed = allowed_subjects(evaluation, test);
        let valid = stem.strip_prefix("test_").is_some_and(valid_unit_filename);
        let behavior_matches = test.explicit_name.as_deref().is_none_or(|name| {
            filename_behavior(stem, &allowed)
                .zip(structured_name(name, &allowed).map(|(_, behavior)| behavior))
                .is_none_or(|(slug, behavior)| behavior_slug_matches(slug, behavior))
        });
        if !valid || !behavior_matches {
            faults.push(path_fault(
                rule,
                &test.source_path,
                format!(
                    "unit test block {} filename does not follow test_<subject>__<behavior>.sql",
                    test.block_index
                ),
                test.explicit_name
                    .as_deref()
                    .and_then(|name| structured_name(name, &allowed))
                    .map_or_else(
                        || "Rename this file to test_<subject>__<behavior>.sql.".to_owned(),
                        |(subject, behavior)| {
                            format!(
                                "Rename this file to test_{}__{}.sql.",
                                slug(subject),
                                slug(behavior)
                            )
                        },
                    ),
            ));
        }
    }
    for scenario in scenarios {
        if !valid_filename_parts(file_stem(&scenario.source_path)) {
            faults.push(path_fault(
                rule,
                &scenario.source_path,
                "scenario filename does not follow <subject>__<behavior>.sql".into(),
                "Rename this file to <business subject>__<behavior>.sql.".into(),
            ));
        }
    }
    faults
}

fn mirroring(
    rule: &RuleMetadata,
    evaluation: &ProjectEvaluationRequest<'_>,
    tests: &[&SqlTestFact],
) -> Vec<Fault> {
    let mut faults: Vec<Fault> = Vec::new();
    for test in tests {
        let Some(expected_parent) = expected_parent(evaluation, test) else {
            continue;
        };
        let actual_parent = Path::new(&test.source_path)
            .parent()
            .map(|path| path.to_string_lossy().replace('\\', "/"))
            .unwrap_or_default();
        if actual_parent != expected_parent {
            faults.push(path_fault(
                rule,
                &test.source_path,
                format!(
                    "unit test block {} resolves to resources mirrored by {expected_parent}/",
                    test.block_index
                ),
                format!("Move this test file beneath {expected_parent}/."),
            ));
        }
    }
    faults
}

fn structured_names(
    rule: &RuleMetadata,
    evaluation: &ProjectEvaluationRequest<'_>,
    tests: &[&SqlTestFact],
) -> Vec<Fault> {
    let mut faults: Vec<Fault> = Vec::new();
    for test in tests {
        let Some(name) = test.explicit_name.as_deref() else {
            faults.push(name_fault(
                rule,
                test,
                "the TEST block has no explicit name",
                None,
            ));
            continue;
        };
        let allowed = allowed_subjects(evaluation, test);
        let Some((subject, behavior)) = structured_name(name, &allowed) else {
            faults.push(name_fault(
                rule,
                test,
                "the TEST name must contain a nonempty subject and behavior separated by '__'",
                None,
            ));
            continue;
        };
        if generic(subject) || generic(behavior) {
            faults.push(name_fault(
                rule,
                test,
                "the TEST name uses a generic subject or behavior",
                None,
            ));
            continue;
        }
        if !allowed.is_empty() && !subject_matches(subject, &allowed) {
            faults.push(name_fault(
                rule,
                test,
                &format!(
                    "the TEST subject '{}' does not identify its resolved target; expected {}",
                    subject,
                    allowed.join(" or ")
                ),
                allowed.first().map(String::as_str),
            ));
        }
    }
    faults
}

fn scenario_descriptions(rule: &RuleMetadata, scenarios: &[&SqlScenarioFact]) -> Vec<Fault> {
    let mut faults: Vec<Fault> = Vec::new();
    for scenario in scenarios {
        let description = scenario.description.as_deref().unwrap_or("").trim();
        let behavior = file_stem(&scenario.source_path)
            .split_once("__")
            .map(|(_, value)| value)
            .unwrap_or("");
        if description.is_empty() || generic(description) || generic(behavior) {
            faults.push(path_fault(
                rule,
                &scenario.source_path,
                "scenario description or filename uses a generic case label".into(),
                "Write a concrete business description and a <subject>__<behavior>.sql filename."
                    .into(),
            ));
        }
    }
    faults
}

fn expected_parent(
    evaluation: &ProjectEvaluationRequest<'_>,
    test: &SqlTestFact,
) -> Option<String> {
    match test.mode {
        SqlTestMode::Model => {
            let mut directories: Vec<Vec<String>> = Vec::new();
            for name in &test.target_model_names {
                let resource = scope_resource(evaluation, ResourceKind::Model, name)?;
                directories.push(relative_parent(resource)?);
            }
            if directories.is_empty() {
                return None;
            }
            let common = common_components(&directories);
            Some(if common.is_empty() {
                format!(
                    "{UNIT_ROOT}/{}",
                    evaluation.request.config.sql_tests.pipeline_directory
                )
            } else {
                format!("{UNIT_ROOT}/{}", common.join("/"))
            })
        }
        SqlTestMode::Macro => direct_expected_parent(&macro_parent_components(evaluation, test)?),
        SqlTestMode::Udf | SqlTestMode::TableFn => {
            direct_expected_parent(&function_parent_components(evaluation, test)?)
        }
    }
}

fn macro_parent_components(
    evaluation: &ProjectEvaluationRequest<'_>,
    test: &SqlTestFact,
) -> Option<Vec<Vec<String>>> {
    let mut parents: Vec<Vec<String>> = Vec::new();
    for resource in &test.tested_resources {
        let declaration = evaluation
            .request
            .scope_index
            .declarations
            .iter()
            .find(|item| {
                matches!(item.kind, DeclarationKind::Macro) && item.name == resource.name
            })?;
        parents.push(match &declaration.owning_path {
            Some(owner) => std::iter::once("macros".to_owned())
                .chain(owner.split('/').map(str::to_owned))
                .collect(),
            None => direct_parent_components(&declaration.path, &declaration.ownership_root)?,
        });
    }
    Some(parents)
}

fn function_parent_components(
    evaluation: &ProjectEvaluationRequest<'_>,
    test: &SqlTestFact,
) -> Option<Vec<Vec<String>>> {
    let mut parents: Vec<Vec<String>> = Vec::new();
    for resource in &test.tested_resources {
        let fact = scope_resource(evaluation, ResourceKind::Function, &resource.name)?;
        parents.push(direct_parent_components(&fact.path, &fact.ownership_root)?);
    }
    Some(parents)
}

fn direct_parent_components(path: &str, root: &str) -> Option<Vec<String>> {
    let path: Vec<&str> = path.split('/').collect();
    let root: Vec<&str> = root.split('/').collect();
    if path.len() <= root.len() || path.get(..root.len()) != Some(root.as_slice()) {
        return None;
    }
    Some(
        path[..path.len() - 1]
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
    )
}

fn direct_expected_parent(parents: &[Vec<String>]) -> Option<String> {
    let common = common_components(parents);
    (!common.is_empty()).then(|| format!("{UNIT_ROOT}/{}", common.join("/")))
}

fn allowed_subjects(evaluation: &ProjectEvaluationRequest<'_>, test: &SqlTestFact) -> Vec<String> {
    if !matches!(test.mode, SqlTestMode::Model) {
        return test
            .tested_resources
            .iter()
            .map(|resource| resource.name.clone())
            .collect();
    }
    if test.target_model_names.len() == 1 {
        return test.target_model_names.clone();
    }
    if test.target_model_names.len() > 1 {
        let mut directories: Vec<Vec<String>> = Vec::new();
        for name in &test.target_model_names {
            let Some(resource) = scope_resource(evaluation, ResourceKind::Model, name) else {
                return Vec::new();
            };
            let Some(parent) = relative_parent(resource) else {
                return Vec::new();
            };
            directories.push(parent);
        }
        let common = common_components(&directories);
        return common
            .last()
            .map_or_else(|| vec!["pipeline".into()], |domain| vec![domain.clone()]);
    }
    Vec::new()
}

fn scope_resource<'a>(
    evaluation: &'a ProjectEvaluationRequest<'_>,
    kind: ResourceKind,
    name: &str,
) -> Option<&'a ScopeResource> {
    evaluation
        .request
        .scope_index
        .resources
        .iter()
        .find(|item| same_resource_kind(&item.kind, &kind) && item.name == name)
}

fn same_resource_kind(left: &ResourceKind, right: &ResourceKind) -> bool {
    matches!(
        (left, right),
        (ResourceKind::Model, ResourceKind::Model)
            | (ResourceKind::Function, ResourceKind::Function)
    )
}

fn relative_parent(resource: &ScopeResource) -> Option<Vec<String>> {
    let path: Vec<&str> = resource.path.split('/').collect();
    let root: Vec<&str> = resource.ownership_root.split('/').collect();
    if path.len() <= root.len() || path.get(..root.len()) != Some(root.as_slice()) {
        return None;
    }
    Some(
        path[root.len()..path.len() - 1]
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
    )
}

fn common_components(values: &[Vec<String>]) -> Vec<String> {
    let Some(first) = values.first() else {
        return Vec::new();
    };
    let mut common: Vec<String> = Vec::new();
    for (index, value) in first.iter().enumerate() {
        let mut shared = true;
        for candidate in values {
            if candidate.get(index) != Some(value) {
                shared = false;
                break;
            }
        }
        if !shared {
            break;
        }
        common.push(value.clone());
    }
    common
}

fn name_fault(
    rule: &RuleMetadata,
    test: &SqlTestFact,
    detail: &str,
    proposed_subject: Option<&str>,
) -> Fault {
    path_fault(
        rule,
        &test.source_path,
        format!("unit test block {} {detail}", test.block_index),
        format!(
            "Add name \"{}__<expected_behavior>\" to this TEST header.",
            proposed_subject.unwrap_or("<resolved_subject>")
        ),
    )
}

fn path_fault(rule: &RuleMetadata, path: &str, message: String, remediation: String) -> Fault {
    Fault {
        code: rule.code.clone(),
        path: path.to_owned(),
        line: 1,
        column: 1,
        message,
        remediation,
    }
}

fn is_beneath(path: &str, root: &str) -> bool {
    path.strip_prefix(root)
        .is_some_and(|suffix| suffix.starts_with('/'))
}

fn file_stem(path: &str) -> &str {
    let filename = path.rsplit('/').next().unwrap_or(path);
    filename.strip_suffix(".sql").unwrap_or(filename)
}

fn valid_filename_parts(value: &str) -> bool {
    value.contains("__") && canonical_identity(value)
}

fn valid_unit_filename(value: &str) -> bool {
    canonical_identity(value)
}

fn canonical_identity(value: &str) -> bool {
    value
        .chars()
        .next()
        .is_some_and(|character| character.is_ascii_lowercase())
        && value
            .chars()
            .last()
            .is_some_and(|character| character.is_ascii_lowercase() || character.is_ascii_digit())
        && value.chars().all(|character| {
            character.is_ascii_lowercase() || character.is_ascii_digit() || character == '_'
        })
}

fn filename_behavior<'a>(stem: &'a str, allowed_subjects: &[String]) -> Option<&'a str> {
    structured_name(stem.strip_prefix("test_").unwrap_or(stem), allowed_subjects)
        .map(|(_, behavior)| behavior)
}

fn structured_name<'a>(name: &'a str, allowed_subjects: &[String]) -> Option<(&'a str, &'a str)> {
    let matched_subject_length = longest_subject_prefix(name, allowed_subjects);
    let (subject, behavior) = matched_subject_length.map_or_else(
        || name.split_once("__"),
        |length| Some((&name[..length], &name[length + 2..])),
    )?;
    let subject = subject.trim();
    let behavior = behavior.trim();
    (!subject.is_empty() && !behavior.is_empty()).then_some((subject, behavior))
}

fn longest_subject_prefix(name: &str, allowed_subjects: &[String]) -> Option<usize> {
    let mut longest: Option<usize> = None;
    for subject in allowed_subjects {
        let Some(suffix) = name.strip_prefix(subject) else {
            continue;
        };
        let Some(behavior) = suffix.strip_prefix("__") else {
            continue;
        };
        if behavior.is_empty() {
            continue;
        }
        if longest.is_none_or(|length| subject.len() > length) {
            longest = Some(subject.len());
        }
    }
    longest
}

fn behavior_slug_matches(filename: &str, behavior: &str) -> bool {
    let behavior = slug(behavior);
    behavior == filename || behavior.starts_with(&format!("{filename}_"))
}

fn subject_matches(subject: &str, allowed: &[String]) -> bool {
    let normalized = slug(subject);
    for value in allowed {
        let candidate = slug(value);
        if normalized == candidate {
            return true;
        }
        if candidate == crate::constants::PIPELINE_SUBJECT
            && normalized
                .split('_')
                .any(|component| component == crate::constants::PIPELINE_SUBJECT)
        {
            return true;
        }
    }
    false
}

fn generic(value: &str) -> bool {
    let normalized = slug(value);
    matches!(
        normalized.as_str(),
        crate::constants::GENERIC_TEST_NAME
            | crate::constants::GENERIC_WORKS_NAME
            | crate::constants::GENERIC_BASIC_NAME
            | crate::constants::GENERIC_SCENARIO_NAME
            | crate::constants::GENERIC_CASE_NAME
    ) || normalized
        .strip_prefix("case_")
        .is_some_and(|suffix| suffix.chars().all(|character| character.is_ascii_digit()))
}

fn slug(value: &str) -> String {
    let mut output = String::new();
    let mut separator = false;
    for character in value.chars().flat_map(char::to_lowercase) {
        if character.is_alphanumeric() {
            if separator && !output.is_empty() {
                output.push('_');
            }
            output.push(character);
            separator = false;
        } else {
            separator = true;
        }
    }
    output
}

pub(crate) fn annotate_empty_input_only_tests(mut request: EvaluateRequest) -> EvaluateRequest {
    for test in &mut request.sql_tests {
        test.empty_input_only = is_empty_input_only(test, &request.dialect);
    }
    let allowed = allowed_tests(&request.config);
    let mut excluded: BTreeMap<String, u32> = BTreeMap::new();
    for test in &request.sql_tests {
        if !test.empty_input_only || is_allowlisted(test, &allowed) {
            continue;
        }
        for name in &test.target_model_names {
            *excluded.entry(name.clone()).or_default() += 1;
        }
    }
    for model in &mut request.models {
        model.empty_input_only_test_count = excluded.get(&model.name).copied().unwrap_or(0);
    }
    request
}

pub(crate) fn minimum_tests_shortfall(model: &Model, minimum: u32) -> Option<String> {
    let excluded = model.empty_input_only_test_count;
    let counted = model.targeting_test_count.saturating_sub(excluded);
    if counted >= minimum {
        return None;
    }
    let mut message = format!(
        "model {:?} has {counted} tests; {minimum} required",
        model.name
    );
    if excluded > 0 {
        let noun = if excluded == 1 { "test" } else { "tests" };
        message.push_str(&format!(
            " ({excluded} empty-input-only {noun} not counted; see {EMPTY_INPUT_RULE_CODE})"
        ));
    }
    Some(message)
}

fn empty_input_only_faults(
    rule: &RuleMetadata,
    config: &RulesConfig,
    tests: &[&SqlTestFact],
) -> Vec<Fault> {
    let allowed = allowed_tests(config);
    let mut faults: Vec<Fault> = Vec::new();
    for test in tests {
        if test.empty_input_only && !is_allowlisted(test, &allowed) {
            faults.push(path_fault(
                rule,
                &test.source_path,
                format!(
                    "unit test block {} ({:?}) mocks only empty inputs and asserts only that no rows are produced",
                    test.block_index, test.name
                ),
                rule.remediation.clone(),
            ));
        }
    }
    for entry in &allowed {
        if !tests.iter().any(|test| test_named(test, entry)) {
            faults.push(path_fault(
                rule,
                PROJECT_CONFIG_PATH,
                format!("stale {ALLOWED_TESTS_OPTION} entry {entry:?} names no existing SQL test"),
                format!(
                    "Remove {entry:?} from [rules.rule_options.{EMPTY_INPUT_RULE_CODE}] {ALLOWED_TESTS_OPTION}, or correct it to the name of an existing test."
                ),
            ));
        }
    }
    faults
}

fn allowed_tests(config: &RulesConfig) -> Vec<String> {
    config.rule_option_strings(EMPTY_INPUT_RULE_CODE, ALLOWED_TESTS_OPTION)
}

fn is_allowlisted(test: &SqlTestFact, allowed: &[String]) -> bool {
    allowed.iter().any(|entry| test_named(test, entry))
}

fn test_named(test: &SqlTestFact, entry: &str) -> bool {
    test.name == entry || (test.case_name.is_some() && test.parent_name.as_deref() == Some(entry))
}

fn is_empty_input_only(test: &SqlTestFact, dialect: &str) -> bool {
    if !matches!(test.mode, SqlTestMode::Model)
        || test.has_macro_mocks
        || test.has_model_query_overrides
        || (test.expected_ctes.is_empty() && test.assertion_ctes.is_empty())
    {
        return false;
    }
    let mut mocks = test
        .authored_ctes
        .iter()
        .filter(|cte| fixture_facts(&cte.name, &cte.sql).mock)
        .peekable();
    mocks.peek().is_some()
        && mocks.all(|cte| empty_relation(cte, dialect))
        && test
            .expected_ctes
            .iter()
            .all(|cte| empty_relation(cte, dialect))
        && test
            .assertion_ctes
            .iter()
            .all(|cte| bare_row_existence(&cte.sql, &test.target_model_names, dialect))
}

fn empty_relation(cte: &SqlTestCteFact, dialect: &str) -> bool {
    if fixture_facts(&cte.name, &cte.sql).empty_fixture_marker {
        return true;
    }
    let Some(query) = parse_fixture_query(&cte.sql, dialect) else {
        return false;
    };
    let SetExpr::Select(select) = query.body.as_ref() else {
        return false;
    };
    query.with.is_none()
        && (limited_to_zero_rows(&query)
            || (filtered_to_zero_rows(select) && !contains_function(&query.order_by)))
}

fn parse_fixture_query(sql: &str, dialect: &str) -> Option<Query> {
    let mut statements = match parse_rule_statements(&normalize_rules_sql(dialect, sql), dialect) {
        Ok(statements) => statements,
        Err(_) => return None,
    };
    match (statements.pop(), statements.is_empty()) {
        (Some(Statement::Query(query)), true) => Some(*query),
        _ => None,
    }
}

fn limited_to_zero_rows(query: &Query) -> bool {
    let limit = match &query.limit_clause {
        Some(LimitClause::LimitOffset {
            limit: Some(limit), ..
        }) => limit,
        Some(LimitClause::OffsetCommaLimit { limit, .. }) => limit,
        _ => return false,
    };
    numeric_literal(limit) == Some(0.0)
}

fn filtered_to_zero_rows(select: &Select) -> bool {
    let global_aggregate_possible = contains_function(select);
    select.having.is_none()
        && group_by_empty(&select.group_by)
        && !global_aggregate_possible
        && select.selection.as_ref().is_some_and(constant_false)
}

fn constant_false(predicate: &Expr) -> bool {
    match unwrap_nested(predicate) {
        Expr::Value(value) => matches!(value.value, Value::Boolean(false)),
        Expr::BinaryOp {
            left,
            op: BinaryOperator::Eq,
            right,
        } => numeric_literal(left)
            .zip(numeric_literal(right))
            .is_some_and(|(left, right)| left != right),
        _ => false,
    }
}

fn numeric_literal(expression: &Expr) -> Option<f64> {
    let Expr::Value(value) = unwrap_nested(expression) else {
        return None;
    };
    let Value::Number(number, _) = &value.value else {
        return None;
    };
    let Ok(parsed) = number.parse::<f64>() else {
        return None;
    };
    Some(parsed)
}

fn bare_row_existence(sql: &str, targets: &[String], dialect: &str) -> bool {
    let Some(query) = parse_fixture_query(sql, dialect) else {
        return false;
    };
    let SetExpr::Select(select) = query.body.as_ref() else {
        return false;
    };
    let [source] = select.from.as_slice() else {
        return false;
    };
    let unfiltered = select.selection.is_none()
        && select.prewhere.is_none()
        && select.having.is_none()
        && select.qualify.is_none()
        && select.connect_by.is_none()
        && select.lateral_views.is_empty()
        && group_by_empty(&select.group_by);
    query.with.is_none()
        && unfiltered
        && source.joins.is_empty()
        && reference_target(&source.relation).is_some_and(|target| targets.contains(&target))
        && !contains_function(&select.projection)
        && !contains_function(&query.order_by)
        && query.limit_clause.is_none()
        && query.fetch.is_none()
        && query_count(&query) == 1
}

fn reference_target(factor: &TableFactor) -> Option<String> {
    if dependency_name(factor).as_deref() != Some("__ref") {
        return None;
    }
    let TableFactor::Table {
        args: Some(arguments),
        ..
    } = factor
    else {
        return None;
    };
    let [FunctionArg::Unnamed(FunctionArgExpr::Expr(argument))] = arguments.args.as_slice() else {
        return None;
    };
    match unwrap_nested(argument) {
        Expr::Identifier(identifier) => Some(identifier.value.clone()),
        Expr::Value(value) => match &value.value {
            Value::SingleQuotedString(name) | Value::DoubleQuotedString(name) => Some(name.clone()),
            _ => None,
        },
        _ => None,
    }
}

fn contains_function<T: Visit>(node: &T) -> bool {
    struct Functions;

    impl Visitor for Functions {
        type Break = ();

        fn pre_visit_expr(&mut self, expression: &Expr) -> ControlFlow<Self::Break> {
            if matches!(expression, Expr::Function(_)) {
                ControlFlow::Break(())
            } else {
                ControlFlow::Continue(())
            }
        }
    }

    node.visit(&mut Functions).is_break()
}

fn query_count(query: &Query) -> usize {
    #[derive(Default)]
    struct Queries {
        count: usize,
    }

    impl Visitor for Queries {
        type Break = ();

        fn pre_visit_query(&mut self, _query: &Query) -> ControlFlow<Self::Break> {
            self.count += 1;
            ControlFlow::Continue(())
        }
    }

    let mut queries = Queries::default();
    let _ = query.visit(&mut queries);
    queries.count
}
